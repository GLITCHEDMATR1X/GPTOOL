from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.panda3d_adapter import discover_panda3d_project, probe_panda3d_environment, resolve_runtime_provider, run_panda3d_smoke
from command_bridge.planner import build_work_order, render_work_order_markdown
from command_bridge.verifier import render_command_verification_markdown, verify_work_order
from game_builder.human_asset_importer import import_human_assets, scan_human_asset_sources
from game_builder.settings_planner import infer_game_settings, render_game_settings_markdown
from game_builder.template_generator import generate_panda3d_template, render_generation_result_markdown
from extensions.panda_xr_vr_builder.commands import command_panda_xr_export, command_panda_xr_proof, command_panda_xr_quality, command_panda_xr_visual_proof
from diagnostics.env_probe import build_probe, finalize_probe
from diagnostics.regression_checker import compare_snapshots
from scanners.project_scanner import scan_project
from validators.asset_validator import validate_assets
from validators.import_validator import validate_imports
from validators.syntax_validator import validate_file
from validators.text_fit_validator import validate_text_fit
from validators.ui_bounds_validator import validate_ui_bounds
from maintenance.package_cleaner import analyze_package, clean_package_tree, create_lean_package_zip, render_package_audit_text

BRIDGE_VERSION = "0.6.6-pass16"
DEFAULT_REPORT_DIR = "reports"
EXCLUDED_DIRS = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules", "dist", "build"}
PANDA3D_PROFILE_NAMES = {"panda3d", "holoverse", "codered", "code_red"}


def _repo_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(path)


def find_python_files(project_root: Path, max_files: int = 5000) -> list[Path]:
    project_root = project_root.resolve()
    files: list[Path] = []
    for path in sorted(project_root.rglob("*.py")):
        try:
            parts = path.relative_to(project_root).parts
        except Exception:
            parts = path.parts
        if any(part in EXCLUDED_DIRS for part in parts):
            continue
        files.append(path)
        if len(files) >= max_files:
            break
    return files


def collect_target_files(project_root: Path, explicit: Iterable[str] | None = None) -> list[Path]:
    if explicit:
        files: list[Path] = []
        for raw in explicit:
            candidate = Path(raw)
            if candidate.is_dir():
                files.extend(find_python_files(candidate))
            else:
                files.append(candidate)
        return sorted({p.resolve() for p in files})
    return find_python_files(project_root)


def validation_status(ok: bool | None, *, skipped: bool = False, failed_as_warning: bool = False) -> str:
    if skipped:
        return "skipped"
    if ok is None:
        return "unknown"
    if failed_as_warning and not ok:
        return "warn"
    return "pass" if ok else "fail"


def add_validation(
    validations: list[dict[str, Any]],
    name: str,
    ok: bool | None,
    details: Any = None,
    *,
    skipped: bool = False,
    failed_as_warning: bool = False,
) -> None:
    item: dict[str, Any] = {
        "name": name,
        "status": validation_status(ok, skipped=skipped, failed_as_warning=failed_as_warning),
    }
    if details is not None:
        item["details"] = details
    validations.append(item)


def summarize_syntax(files: list[Path]) -> dict[str, Any]:
    results = [validate_file(path) for path in files]
    failures = [item for item in results if not item.get("ok")]
    return {
        "checked_file_count": len(results),
        "failed_file_count": len(failures),
        "ok": not failures,
        "failures": failures[:50],
    }


def summarize_imports(files: list[Path], project_root: Path) -> dict[str, Any]:
    results = [validate_imports(path, project_root=project_root) for path in files]
    failures = [item for item in results if not item.get("ok")]
    missing_roots = sorted({root for item in failures for root in item.get("missing", [])})
    return {
        "checked_file_count": len(results),
        "failed_file_count": len(failures),
        "missing_roots": missing_roots,
        "ok": not failures,
        "failures": failures[:50],
    }


def summarize_ui(files: list[Path], width: int = 1920, height: int = 1080) -> dict[str, Any]:
    results = [validate_ui_bounds(path, width=width, height=height) for path in files]
    warnings = [item for item in results if not item.get("ok")]
    return {
        "checked_file_count": len(results),
        "warning_file_count": len(warnings),
        "ok": not warnings,
        "warnings": warnings[:50],
    }


def summarize_text(files: list[Path]) -> dict[str, Any]:
    results = [validate_text_fit(path) for path in files]
    warnings = [item for item in results if not item.get("ok")]
    return {
        "checked_file_count": len(results),
        "warning_file_count": len(warnings),
        "ok": not warnings,
        "warnings": warnings[:50],
    }


def build_latest_report(
    *,
    project_root: Path,
    profile: str,
    requested_change: str,
    files_touched: list[str],
    validations: list[dict[str, Any]],
    project_scan: dict[str, Any] | None = None,
    regression: dict[str, Any] | None = None,
    screenshot_review: dict[str, Any] | None = None,
    work_order: dict[str, Any] | None = None,
    command_verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blocker_statuses = {"fail"}
    deliverable = not any(item.get("status") in blocker_statuses for item in validations)
    limitations: list[str] = []
    blockers: list[str] = []
    for item in validations:
        status = item.get("status")
        name = item.get("name")
        if status in blocker_statuses:
            blockers.append(str(name))
        elif status in {"warn", "skipped", "unknown"}:
            limitations.append(f"{name}: {status}")
    if not limitations:
        limitations.append("No known limitations were detected by the enabled validators.")
    return {
        "bridge_version": BRIDGE_VERSION,
        "profile": profile,
        "requested_change": requested_change,
        "files_touched": files_touched,
        "validations": validations,
        "work_order": work_order,
        "command_verification": command_verification,
        "mechanic_manifest": None,
        "project_scan": project_scan,
        "regression": regression,
        "screenshot_review": screenshot_review,
        "pre_submit_gate": None,
        "mechanic_acceptance": None,
        "step_gate": None,
        "delivery": {
            "deliverable": deliverable,
            "blockers": blockers,
            "known_limitations": limitations,
            "screenshot_path": None,
            "artifacts": [],
        },
    }


def write_report(report: dict[str, Any], report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "latest_report.json"
    md_path = report_dir / "latest_report.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown_report(report), encoding="utf-8")
    return json_path, md_path


def render_markdown_report(report: dict[str, Any]) -> str:
    delivery = report.get("delivery", {})
    lines = [
        "# GPT Game Generation Bridge Report",
        "",
        f"- Bridge version: `{report.get('bridge_version')}`",
        f"- Profile: `{report.get('profile')}`",
        f"- Requested change: {report.get('requested_change')}",
        f"- Delivery allowed: **{'YES' if delivery.get('deliverable') else 'NO'}**",
        "",
        "## Validations",
        "",
    ]
    for item in report.get("validations", []):
        lines.append(f"- **{item.get('name')}**: `{item.get('status')}`")
    work_order = report.get("work_order") or {}
    if work_order:
        lines.extend(["", "## AI Work Order", ""])
        lines.append(f"- Command ID: `{work_order.get('command_id')}`")
        lines.append(f"- Intents: {', '.join(work_order.get('intents') or [])}")
        must_do = work_order.get("must_do") or []
        if must_do:
            lines.append("- Must-do count: " + str(len(must_do)))
    command_verification = report.get("command_verification") or {}
    if command_verification:
        cv_delivery = command_verification.get("delivery") or {}
        lines.extend(["", "## AI Command Verification", ""])
        lines.append(f"- Command delivery allowed: **{'YES' if cv_delivery.get('deliverable') else 'NO'}**")
        for item in command_verification.get("validations", [])[:12]:
            lines.append(f"- **{item.get('name')}**: `{item.get('status')}`")
    blockers = delivery.get("blockers") or []
    if blockers:
        lines.extend(["", "## Blockers", ""])
        for item in blockers:
            lines.append(f"- {item}")
    lines.extend(["", "## Known Limitations", ""])
    for item in delivery.get("known_limitations", []):
        lines.append(f"- {item}")
    scan = report.get("project_scan") or {}
    summary = scan.get("summary") if isinstance(scan, dict) else None
    if summary:
        lines.extend([
            "",
            "## Project Summary",
            "",
            f"- Files: {summary.get('file_count')}",
            f"- Python files: {summary.get('code_file_count')}",
            f"- Assets: {summary.get('asset_file_count')}",
            f"- Likely profile: `{summary.get('likely_profile')}`",
        ])
    return "\n".join(lines) + "\n"


def command_scan(args: argparse.Namespace) -> int:
    project_root = Path(args.project).resolve()
    report = scan_project(project_root, max_files=args.max_files)
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2) if args.json else render_scan_text(report))
    return 0


def render_scan_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    return "\n".join([
        f"Project: {report['project_root']}",
        f"Likely profile: {summary['likely_profile']}",
        f"Files: {summary['file_count']}",
        f"Python files: {summary['code_file_count']}",
        f"Assets: {summary['asset_file_count']}",
    ])


def _is_panda_profile(profile: str) -> bool:
    return profile.lower().replace("-", "_") in PANDA3D_PROFILE_NAMES


def load_json_file(path: str | Path) -> dict[str, Any]:
    p = Path(path).resolve()
    return json.loads(p.read_text(encoding="utf-8"))


def read_changed_files(raw_items: list[str] | None) -> list[str]:
    if not raw_items:
        return []
    files: list[str] = []
    for raw in raw_items:
        if not raw:
            continue
        candidate = Path(raw)
        if candidate.exists() and candidate.is_file() and candidate.suffix.lower() in {".txt", ".lst"}:
            for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    files.append(line)
        else:
            files.append(raw)
    return files


def infer_changed_files_from_regression(regression: dict[str, Any] | None) -> list[str]:
    if not isinstance(regression, dict):
        return []
    paths: list[str] = []
    for key in ("changed_files", "added_files", "removed_files", "modified_files"):
        value = regression.get(key)
        if isinstance(value, list):
            paths.extend(str(item) for item in value)
    details = regression.get("details")
    if isinstance(details, dict):
        for key in ("changed_files", "added_files", "removed_files", "modified_files"):
            value = details.get(key)
            if isinstance(value, list):
                paths.extend(str(item) for item in value)
    return sorted(set(paths))


def _run_panda3d_validations(args: argparse.Namespace, project_root: Path, validations: list[dict[str, Any]]) -> None:
    runtime = resolve_runtime_provider(
        project_root,
        requested=getattr(args, "runtime", "auto"),
        runtime_path=getattr(args, "runtime_path", None),
        packaged_exe=getattr(args, "exe", None),
        command=getattr(args, "smoke_command", None),
    )
    selected_runtime = runtime.get("selected")
    runtime_required = bool(getattr(args, "smoke", False) or getattr(args, "require_panda3d", False))
    add_validation(
        validations,
        "panda3d_runtime_provider",
        bool(runtime.get("ready")),
        runtime,
        failed_as_warning=not runtime_required,
    )

    env_probe = runtime.get("environment") if isinstance(runtime, dict) else None
    if selected_runtime in {"system_python", "portable_python"}:
        require_ready = bool(getattr(args, "require_panda3d", False) or getattr(args, "smoke", False))
        add_validation(
            validations,
            "panda3d_dependency_probe",
            bool(env_probe and env_probe.get("ready")),
            env_probe,
            failed_as_warning=not require_ready,
        )
    elif selected_runtime == "packaged_exe":
        add_validation(
            validations,
            "panda3d_dependency_probe",
            None,
            "Skipped. Packaged executable mode does not require Panda3D imports in the bridge Python environment.",
            skipped=True,
        )
    elif selected_runtime == "mock_display":
        add_validation(
            validations,
            "panda3d_dependency_probe",
            bool(not getattr(args, "require_panda3d", False)),
            "Mock display fallback selected. Real Panda3D import/render proof is unverified until a system, portable, or packaged runtime is supplied.",
            failed_as_warning=not bool(getattr(args, "require_panda3d", False)),
        )

    discovery = discover_panda3d_project(project_root, explicit_entry=getattr(args, "entry", None), max_files=getattr(args, "max_files", 5000))
    discovered = bool(getattr(args, "smoke_command", None) or getattr(args, "exe", None) or selected_runtime == "packaged_exe" or discovery.get("selected_entry"))
    add_validation(
        validations,
        "panda3d_project_discovery",
        discovered,
        discovery,
        failed_as_warning=not bool(getattr(args, "smoke", False) or getattr(args, "entry", None) or getattr(args, "smoke_command", None) or getattr(args, "exe", None)),
    )

    wants_smoke = bool(getattr(args, "smoke", False) or getattr(args, "smoke_command", None) or getattr(args, "exe", None))
    if wants_smoke:
        smoke = run_panda3d_smoke(
            project_root,
            entry=getattr(args, "entry", None),
            command=getattr(args, "smoke_command", None),
            timeout=int(getattr(args, "timeout", 20)),
            screenshot_path=getattr(args, "screenshot_path", None),
            require_screenshot=bool(getattr(args, "require_screenshot", False)),
            proof_path=getattr(args, "proof_path", None),
            require_proof=bool(getattr(args, "require_proof", False)),
            frames=int(getattr(args, "frames", 4)),
            window_type=getattr(args, "window_type", "default"),
            extra_env=getattr(args, "extra_env", None),
            runtime_provider=getattr(args, "runtime", "auto"),
            runtime_path=getattr(args, "runtime_path", None),
            packaged_exe=getattr(args, "exe", None),
        )
        is_mock = (smoke.get("runtime_provider", {}) or {}).get("selected") == "mock_display"
        add_validation(
            validations,
            "panda3d_runtime_smoke",
            bool(smoke.get("ok")),
            smoke,
            failed_as_warning=is_mock and not bool(getattr(args, "require_screenshot", False)),
        )
        screenshot = smoke.get("screenshot", {}) if isinstance(smoke, dict) else {}
        if is_mock and not bool(getattr(args, "require_screenshot", False)):
            add_validation(
                validations,
                "panda3d_visual_proof",
                False,
                "Mock display mode ran non-render checks only. Real screenshot/window proof remains unverified.",
                failed_as_warning=True,
            )
        proof = smoke.get("proof", {}) if isinstance(smoke, dict) else {}
        if getattr(args, "require_proof", False) or getattr(args, "proof_path", None):
            add_validation(
                validations,
                "panda3d_scene_proof",
                bool(proof.get("exists")),
                proof,
                failed_as_warning=not bool(getattr(args, "require_proof", False)),
            )
        if getattr(args, "require_screenshot", False) or getattr(args, "screenshot_path", None):
            add_validation(
                validations,
                "panda3d_screenshot_proof",
                bool(screenshot.get("exists")),
                screenshot,
                failed_as_warning=not bool(getattr(args, "require_screenshot", False)),
            )
    else:
        add_validation(
            validations,
            "panda3d_runtime_smoke",
            None,
            "Skipped. Re-run with --smoke plus --entry, --smoke-command, --runtime portable, or --runtime packaged-exe --exe path/to/game.exe.",
            skipped=True,
        )

def run_full_pass(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    project_root = Path(args.project).resolve()
    report_dir = Path(args.report_dir).resolve()
    profile = args.profile
    py_files = collect_target_files(project_root)
    validations: list[dict[str, Any]] = []
    work_order = load_json_file(args.work_order) if getattr(args, "work_order", None) else None
    command_verification = None
    changed_files = read_changed_files(getattr(args, "changed_files", None))

    if work_order:
        add_validation(validations, "ai_work_order_loaded", work_order.get("schema_version") == "work_order.v1", {
            "command_id": work_order.get("command_id"),
            "source_command": work_order.get("source_command"),
            "must_do_count": len(work_order.get("must_do") or []),
            "must_not_do_count": len(work_order.get("must_not_do") or []),
        })
        if args.requested_change in {"one-command validation pass", "full validation pass"}:
            args.requested_change = str(work_order.get("source_command") or args.requested_change)

    env = finalize_probe(build_probe())
    add_validation(validations, "environment_probe", True, {
        "python_version": env.get("platform", {}).get("python_version"),
        "panda3d_profile_ready": env.get("capabilities", {}).get("panda3d_profile_ready"),
        "notes": env.get("capabilities", {}).get("notes", []),
    })

    project_scan = scan_project(project_root, max_files=args.max_files)
    add_validation(validations, "project_scan", True, project_scan.get("summary"))

    if py_files:
        syntax = summarize_syntax(py_files)
        add_validation(validations, "python_syntax", syntax["ok"], syntax)

        imports = summarize_imports(py_files, project_root)
        add_validation(validations, "import_resolution", imports["ok"], imports)

        assets = validate_assets(project_root)
        add_validation(validations, "asset_references", assets.get("ok"), assets)

        ui = summarize_ui(py_files, width=args.width, height=args.height)
        add_validation(validations, "ui_bounds_static", ui["ok"], ui, failed_as_warning=True)

        text = summarize_text(py_files)
        add_validation(validations, "text_fit_static", text["ok"], text, failed_as_warning=True)
    else:
        add_validation(validations, "python_syntax", None, "No Python files discovered.", skipped=True)
        add_validation(validations, "import_resolution", None, "No Python files discovered.", skipped=True)
        add_validation(validations, "asset_references", None, "No Python files discovered.", skipped=True)
        add_validation(validations, "ui_bounds_static", None, "No Python files discovered.", skipped=True)
        add_validation(validations, "text_fit_static", None, "No Python files discovered.", skipped=True)

    if _is_panda_profile(profile):
        _run_panda3d_validations(args, project_root, validations)

    regression = None
    if args.baseline:
        regression = compare_snapshots(project_root, Path(args.baseline).resolve(), allowed_edit_targets=args.allow)
        risk = regression.get("summary", {}).get("regression_risk")
        add_validation(validations, "regression_diff", risk in {"low", "medium"}, regression, failed_as_warning=(risk == "medium"))
    else:
        add_validation(validations, "regression_diff", None, "No baseline supplied.", skipped=True)

    if work_order:
        command_verification = verify_work_order(
            project_root,
            work_order,
            latest_report=None,
            changed_files=changed_files or infer_changed_files_from_regression(regression),
            strict_static=bool(getattr(args, "strict_static", False)),
            max_files=int(getattr(args, "max_files", 5000)),
        )
        add_validation(validations, "ai_command_verification", command_verification.get("delivery", {}).get("deliverable"), command_verification)

    report = build_latest_report(
        project_root=project_root,
        profile=profile,
        requested_change=args.requested_change,
        files_touched=[],
        validations=validations,
        project_scan=project_scan,
        regression=regression,
        work_order=work_order,
        command_verification=command_verification,
    )
    json_path, md_path = write_report(report, report_dir)
    code = 0 if report["delivery"]["deliverable"] else 1
    if args.json:
        payload = json.dumps(report, indent=2) + "\n"
    else:
        lines = [
            f"Report JSON: {json_path}",
            f"Report Markdown: {md_path}",
            f"Delivery allowed: {'YES' if report['delivery']['deliverable'] else 'NO'}",
        ]
        lines.extend(f"[{item['status'].upper()}] {item['name']}" for item in validations)
        payload = "\n".join(lines) + "\n"
    if getattr(args, "_cli_exit", False):
        os.write(1, payload.encode("utf-8", errors="replace"))
        os._exit(code)
    print(payload, end="")
    return report, code


def command_validate(args: argparse.Namespace) -> int:
    args._cli_exit = True
    _report, code = run_full_pass(args)
    return code


def command_screenshot_review(args: argparse.Namespace) -> int:
    from reviewers.screenshot_reviewer import review_image

    result = review_image(Path(args.image).resolve(), args.layout_profile)
    out = Path(args.output).resolve() if args.output else Path(DEFAULT_REPORT_DIR).resolve() / "screenshot_review.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    overall = float(result.get("scores", {}).get("overall", 0.0))
    high_count = int(result.get("summary", {}).get("high_severity_issue_count", 0))
    passed = overall >= args.min_score and high_count == 0
    print(f"Screenshot review: {'PASS' if passed else 'FAIL'} overall={overall:.2f} high_issues={high_count} output={out}")
    return 0 if passed else 1


def command_regression(args: argparse.Namespace) -> int:
    report = compare_snapshots(Path(args.current).resolve(), Path(args.baseline).resolve(), allowed_edit_targets=args.allow)
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2) if args.json else json.dumps(report["summary"], indent=2))
    risk = report.get("summary", {}).get("regression_risk")
    return 0 if risk in {"low", "medium"} else 1


def command_report(args: argparse.Namespace) -> int:
    path = Path(args.report).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    print(render_markdown_report(data))
    return 0



def _read_command_text(command: str = "", command_file: str | None = None) -> str:
    if command_file:
        return Path(command_file).resolve().read_text(encoding="utf-8")
    return command or ""



def command_package_audit(args: argparse.Namespace) -> int:
    report = analyze_package(
        Path(args.root).resolve(),
        include_examples=bool(args.include_examples),
        include_generated_logs=bool(args.include_generated_logs),
    )
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2) if args.json else render_package_audit_text(report))
    return 0 if report.get("ok") else 1


def command_clean_package(args: argparse.Namespace) -> int:
    report = clean_package_tree(
        Path(args.root).resolve(),
        apply=bool(args.apply),
        include_examples=bool(args.include_examples),
        include_generated_logs=bool(args.include_generated_logs),
    )
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        mode = "removed" if args.apply else "would remove"
        print(f"Clean package: {mode} {report.get('candidate_count')} candidates / {report.get('candidate_size_bytes', 0)} bytes")
        if not args.apply:
            print("Re-run with --apply to remove the candidates from this tree.")
    return 0 if report.get("ok") else 1


def command_package_lean_zip(args: argparse.Namespace) -> int:
    report = create_lean_package_zip(
        Path(args.source_root).resolve(),
        Path(args.output_zip).resolve(),
        include_examples=bool(args.include_examples),
        include_generated_logs=bool(args.include_generated_logs),
        include_pycache=bool(args.include_pycache),
    )
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Lean package zip: {'PASS' if report.get('ok') else 'FAIL'}")
        print(f"Output: {report.get('output_zip')}")
        print(f"Files: {report.get('added_file_count')} added / {report.get('skipped_file_count')} skipped")
        print(f"Zip size: {report.get('zip_size_bytes')} bytes")
    return 0 if report.get("ok") else 1

def command_plan_game(args: argparse.Namespace) -> int:
    project_root = Path(args.project).resolve()
    command_text = _read_command_text(args.command, args.command_file)
    if not command_text.strip():
        print("plan-game requires --command text or --command-file path", file=sys.stderr)
        return 2
    settings = infer_game_settings(project_root, args.profile, command_text)
    out = Path(args.output).resolve() if args.output else project_root / DEFAULT_REPORT_DIR / "game_settings.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    md_path = out.with_suffix(".md")
    md_path.write_text(render_game_settings_markdown(settings), encoding="utf-8")
    if args.json:
        print(json.dumps(settings, indent=2))
    else:
        project = settings.get("project", {})
        world = settings.get("world", {})
        print(f"Game settings: {out}")
        print(f"Game settings Markdown: {md_path}")
        print(f"Title: {project.get('title')}")
        print(f"Template: {project.get('template_version')}")
        print(f"Regions: {len(world.get('regions') or [])}")
        print(f"Characters: {len(settings.get('characters') or [])}")
        print("Next: python bridge.py generate-template <output_dir> --settings " + str(out))
    return 0


def command_generate_template(args: argparse.Namespace) -> int:
    settings_path = Path(args.settings).resolve()
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    result = generate_panda3d_template(args.output_dir, settings, overwrite=bool(args.force))
    out = Path(args.report).resolve() if args.report else Path(args.output_dir).resolve() / "reports" / "template_generation_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    out.with_suffix(".md").write_text(render_generation_result_markdown(result), encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Template generation: {'PASS' if result.get('ok') else 'FAIL'}")
        print(f"Output: {result.get('output_dir')}")
        print(f"Report: {out}")
        if result.get("ok"):
            print(f"Entry: {result.get('entry')}")
            print(f"Settings: {result.get('settings')}")
        else:
            print(f"Reason: {result.get('reason')}")
    return 0 if result.get("ok") else 1


def command_generate_game(args: argparse.Namespace) -> int:
    command_text = _read_command_text(args.command, args.command_file)
    if not command_text.strip():
        print("generate-game requires --command text or --command-file path", file=sys.stderr)
        return 2
    output_dir = Path(args.output_dir).resolve()
    settings = infer_game_settings(output_dir, args.profile, command_text)
    result = generate_panda3d_template(output_dir, settings, overwrite=bool(args.force))
    report_dir = output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    settings_report = report_dir / "planned_game_settings.json"
    settings_report.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    settings_report.with_suffix(".md").write_text(render_game_settings_markdown(settings), encoding="utf-8")
    gen_report = report_dir / "template_generation_result.json"
    gen_report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    gen_report.with_suffix(".md").write_text(render_generation_result_markdown(result), encoding="utf-8")
    payload = {
        "schema_version": "generate_game_result.v1",
        "bridge_version": BRIDGE_VERSION,
        "settings": settings,
        "generation": result,
        "reports": {
            "settings": str(settings_report),
            "generation": str(gen_report),
        },
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        project = settings.get("project", {})
        print(f"Generate game: {'PASS' if result.get('ok') else 'FAIL'}")
        print(f"Title: {project.get('title')}")
        print(f"Output: {result.get('output_dir')}")
        print(f"Settings: {result.get('settings')}")
        print(f"Entry: {result.get('entry')}")
        print(f"Reports: {report_dir}")
        if result.get("ok"):
            print("Next inside generated project: python main.py --settings-check")
            print("Then, with Panda3D installed or portable runtime: python main.py")
        else:
            print(f"Reason: {result.get('reason')}")
    return 0 if result.get("ok") else 1


def command_scan_human_assets(args: argparse.Namespace) -> int:
    search_root = Path(args.search_root).resolve()
    report = scan_human_asset_sources(
        search_root,
        max_files=args.max_files,
        min_score=args.min_score,
        prefer_tokens=tuple(args.prefer or []),
        require_tokens=tuple(args.require or []),
        rigged_only=bool(args.rigged_only),
    )
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        summary = report.get("summary") or {}
        print(f"Human asset scan: {'PASS' if report.get('ok') else 'FAIL'}")
        print(f"Search root: {report.get('search_root')}")
        print(f"Candidates: {summary.get('candidate_count', 0)}")
        print(f"Rigged candidates: {summary.get('rigged_candidate_count', 0)}")
        for item in (report.get("candidates") or [])[:12]:
            details = item.get("summary") or {}
            skin = "skin" if details.get("has_skin") else "no-skin"
            anim = "anim" if details.get("has_animation") else "no-anim"
            print(f"- [{item.get('score')}] {item.get('relative_path')} ({item.get('asset_type')}, {skin}, {anim})")
        if args.output:
            print(f"Report: {Path(args.output).resolve()}")
    return 0 if report.get("ok") else 1


def command_import_human_assets(args: argparse.Namespace) -> int:
    project_root = Path(args.project).resolve()
    search_root = Path(args.search_root).resolve() if args.search_root else ROOT.parent
    report = import_human_assets(
        project_root,
        search_root,
        limit=args.limit,
        animation_limit=args.animation_limit,
        include_large=bool(args.include_large),
        overwrite=bool(args.force),
        update_settings=not bool(args.no_settings_update),
        export_formats=tuple(args.export_formats or []),
        prefer_tokens=tuple(args.prefer or []),
        require_tokens=tuple(args.require or []),
        rigged_only=bool(args.rigged_only),
        clean=bool(args.clean),
    )
    out = Path(args.output).resolve() if args.output else project_root / DEFAULT_REPORT_DIR / "human_asset_import.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    out.with_suffix(".md").write_text(render_human_asset_import_markdown(report), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Human asset import: {'PASS' if report.get('ok') else 'FAIL'}")
        print(f"Project: {project_root}")
        print(f"Search root: {search_root}")
        print(f"Report: {out}")
        if report.get("ok"):
            print(f"Manifest: {report.get('manifest')}")
            print(f"Base assets: {report.get('base_asset_count')}")
            print(f"Animation assets: {report.get('animation_asset_count')}")
            summary = report.get("export_summary") or {}
            print(f"Exports: {summary.get('ok_count', 0)} ok, {summary.get('failed_count', 0)} skipped/failed")
            print(f"Settings updated: {'YES' if report.get('settings_updated') else 'NO'}")
        else:
            print(f"Reason: {report.get('reason')}")
    return 0 if report.get("ok") else 1


def render_human_asset_import_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Human Asset Import",
        "",
        f"- Status: **{'PASS' if report.get('ok') else 'FAIL'}**",
        f"- Project: `{report.get('project_root')}`",
        f"- Search root: `{report.get('search_root')}`",
    ]
    if not report.get("ok"):
        lines.append(f"- Reason: {report.get('reason')}")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            f"- Manifest: `{report.get('manifest')}`",
            f"- Base assets: `{report.get('base_asset_count')}`",
            f"- Animation assets: `{report.get('animation_asset_count')}`",
            f"- Exports OK: `{(report.get('export_summary') or {}).get('ok_count', 0)}`",
            f"- Exports skipped/failed: `{(report.get('export_summary') or {}).get('failed_count', 0)}`",
            "",
            "## Selected Base Assets",
            "",
        ]
    )
    for item in report.get("selected_base_assets") or []:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Selected Animation Assets", ""])
    for item in report.get("selected_animation_assets") or []:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Export Notes", ""])
    for item in (report.get("exports") or [])[:24]:
        status = "ok" if item.get("ok") else "skipped"
        lines.append(f"- `{item.get('format')}` {status}: {item.get('reason')}")
    return "\n".join(lines) + "\n"

def command_plan_command(args: argparse.Namespace) -> int:
    project_root = Path(args.project).resolve()
    command_text = args.command
    if args.command_file:
        command_text = Path(args.command_file).resolve().read_text(encoding="utf-8")
    if not command_text or not command_text.strip():
        print("plan-command requires --command text or --command-file path", file=sys.stderr)
        return 2
    order = build_work_order(project_root, args.profile, command_text)
    out = Path(args.output).resolve() if args.output else project_root / DEFAULT_REPORT_DIR / "work_order.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(order, indent=2), encoding="utf-8")
    md_path = out.with_suffix(".md")
    md_path.write_text(render_work_order_markdown(order), encoding="utf-8")
    if args.json:
        print(json.dumps(order, indent=2))
    else:
        print(f"Work order: {out}")
        print(f"Work order Markdown: {md_path}")
        print(f"Command ID: {order.get('command_id')}")
        print("Must do:")
        for item in order.get("must_do", [])[:8]:
            print(f"- {item}")
        print("Must not do:")
        for item in order.get("must_not_do", [])[:8]:
            print(f"- {item}")
    return 0


def command_verify_command(args: argparse.Namespace) -> int:
    project_root = Path(args.project).resolve()
    work_order = load_json_file(args.work_order)
    latest_report = load_json_file(args.report) if args.report else None
    changed_files = read_changed_files(args.changed_files)
    result = verify_work_order(
        project_root,
        work_order,
        latest_report=latest_report,
        changed_files=changed_files,
        strict_static=bool(args.strict_static),
        max_files=args.max_files,
    )
    out = Path(args.output).resolve() if args.output else project_root / DEFAULT_REPORT_DIR / "command_verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    out.with_suffix(".md").write_text(render_command_verification_markdown(result), encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Command verification: {'PASS' if result.get('delivery', {}).get('deliverable') else 'FAIL'}")
        print(f"Report: {out}")
        for item in result.get("validations", []):
            print(f"[{item.get('status', '').upper()}] {item.get('name')}")
    return 0 if result.get("delivery", {}).get("deliverable") else 1


def command_panda3d_doctor(args: argparse.Namespace) -> int:
    project_root = Path(args.project).resolve()
    report = {
        "bridge_version": BRIDGE_VERSION,
        "project_root": str(project_root),
        "environment": probe_panda3d_environment(),
        "discovery": discover_panda3d_project(project_root, explicit_entry=args.entry, max_files=args.max_files),
    }
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        env = report["environment"]
        disc = report["discovery"]
        print(f"Panda3D ready: {'YES' if env.get('ready') else 'NO'}")
        print(f"Selected entry: {disc.get('selected_entry') or 'none'}")
        for note in env.get("notes", []) + disc.get("notes", []):
            print(f"- {note}")
    return 0 if report["environment"].get("ready") and report["discovery"].get("selected_entry") else 1


def command_panda3d_runtimes(args: argparse.Namespace) -> int:
    project_root = Path(args.project).resolve()
    report = {
        "bridge_version": BRIDGE_VERSION,
        "project_root": str(project_root),
        "requested_runtime": args.runtime,
        "runtime_provider": resolve_runtime_provider(
            project_root,
            requested=args.runtime,
            runtime_path=args.runtime_path,
            packaged_exe=args.exe,
            command=args.smoke_command,
        ),
    }
    if args.output:
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        provider = report["runtime_provider"]
        print(f"Runtime selected: {provider.get('selected') or 'none'}")
        print(f"Ready: {'YES' if provider.get('ready') else 'NO'}")
        print(f"Visual capable: {'YES' if provider.get('visual_capable') else 'NO'}")
        if provider.get("python_executable"):
            print(f"Python: {provider.get('python_executable')}")
        if provider.get("packaged_exe"):
            print(f"Executable: {provider.get('packaged_exe')}")
        for note in provider.get("notes", [])[:10]:
            print(f"- {note}")
    return 0 if report["runtime_provider"].get("ready") else 1


def command_panda3d_smoke(args: argparse.Namespace) -> int:
    project_root = Path(args.project).resolve()
    report = run_panda3d_smoke(
        project_root,
        entry=args.entry,
        command=args.smoke_command,
        timeout=args.timeout,
        screenshot_path=args.screenshot_path,
        require_screenshot=args.require_screenshot,
        proof_path=args.proof_path,
        require_proof=args.require_proof,
        frames=args.frames,
        window_type=args.window_type,
        extra_env=args.extra_env,
        runtime_provider=args.runtime,
        runtime_path=args.runtime_path,
        packaged_exe=args.exe,
    )
    if args.output:
        out = Path(args.output).resolve()
    else:
        out = project_root / DEFAULT_REPORT_DIR / "panda3d_smoke_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Panda3D smoke: {'PASS' if report.get('ok') else 'FAIL'}")
        print(f"Report: {out}")
        print(f"Screenshot: {report.get('screenshot', {}).get('path')} exists={report.get('screenshot', {}).get('exists')}")
        for item in report.get("next_actions", [])[:6]:
            print(f"- {item}")
    return 0 if report.get("ok") else 1


def add_validation_args(parser: argparse.ArgumentParser, default_change: str) -> None:
    parser.add_argument("project")
    parser.add_argument("--profile", default="generic_python")
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--requested-change", default=default_change)
    parser.add_argument("--baseline", help="Optional baseline directory for regression comparison.")
    parser.add_argument("--allow", nargs="*", default=None, help="Optional allowed changed paths for regression scope checks.")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--max-files", type=int, default=5000)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="For Panda3D profiles, launch the runtime smoke adapter.")
    parser.add_argument("--entry", help="Relative or absolute Panda3D entry script, such as main.py.")
    parser.add_argument("--smoke-command", help="Explicit command to run for Panda3D smoke testing.")
    parser.add_argument("--runtime", default="auto", choices=["auto", "system", "system_python", "portable", "portable_python", "packaged", "packaged-exe", "packaged_exe", "mock", "mock_display"], help="Runtime provider for Panda3D smoke: auto, system, portable, packaged-exe, or mock.")
    parser.add_argument("--runtime-path", help="Path to a reusable portable Python/Panda3D runtime folder or python executable.")
    parser.add_argument("--exe", help="Path to a packaged game executable for player-route smoke testing.")
    parser.add_argument("--timeout", type=int, default=20, help="Runtime smoke timeout in seconds.")
    parser.add_argument("--screenshot-path", help="Expected screenshot path for runtime smoke proof.")
    parser.add_argument("--require-screenshot", action="store_true", help="Block delivery if runtime smoke does not produce a screenshot.")
    parser.add_argument("--proof-path", help="Expected JSON scene-proof path for runtime smoke validation.")
    parser.add_argument("--require-proof", action="store_true", help="Block delivery if runtime smoke does not write a scene-proof JSON file.")
    parser.add_argument("--require-panda3d", action="store_true", help="Block delivery if Panda3D core packages are unavailable.")
    parser.add_argument("--frames", type=int, default=4, help="Frame delay hint for the optional smoke screenshot hook.")
    parser.add_argument("--window-type", default="default", choices=["default", "onscreen", "offscreen", "none"], help="Window type hint exposed to the game through GPT_BRIDGE_WINDOW_TYPE.")
    parser.add_argument("--extra-env", nargs="*", default=None, help="Extra KEY=VALUE environment variables for runtime smoke.")
    parser.add_argument("--work-order", help="AI command work order JSON generated by plan-command.")
    parser.add_argument("--changed-files", nargs="*", default=None, help="Changed file paths or .txt lists for work-order scope verification.")
    parser.add_argument("--strict-static", action="store_true", help="Treat static forbidden term hits from the work order as blockers instead of warnings.")


def add_panda_smoke_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project")
    parser.add_argument("--entry", help="Relative or absolute Panda3D entry script, such as main.py.")
    parser.add_argument("--smoke-command", help="Explicit command to run instead of an entry script.")
    parser.add_argument("--runtime", default="auto", choices=["auto", "system", "system_python", "portable", "portable_python", "packaged", "packaged-exe", "packaged_exe", "mock", "mock_display"])
    parser.add_argument("--runtime-path", help="Path to a reusable portable Python/Panda3D runtime folder or python executable.")
    parser.add_argument("--exe", help="Path to a packaged game executable for player-route smoke testing.")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--screenshot-path")
    parser.add_argument("--require-screenshot", action="store_true")
    parser.add_argument("--proof-path")
    parser.add_argument("--require-proof", action="store_true")
    parser.add_argument("--frames", type=int, default=4)
    parser.add_argument("--window-type", default="default", choices=["default", "onscreen", "offscreen", "none"])
    parser.add_argument("--extra-env", nargs="*", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GPT Game Generation Bridge master CLI.")
    parser.add_argument("--version", action="version", version=f"GPT Game Generation Bridge {BRIDGE_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    package_audit = sub.add_parser("package-audit", help="Audit GPTOOL bundle size and safe cleanup candidates.")
    package_audit.add_argument("root", nargs="?", default=str(ROOT))
    package_audit.add_argument("--include-examples", action="store_true", help="Treat examples as required instead of cleanup candidates.")
    package_audit.add_argument("--include-generated-logs", action="store_true", help="Treat generated logs/reports as required instead of cleanup candidates.")
    package_audit.add_argument("--json", action="store_true")
    package_audit.add_argument("--output")
    package_audit.set_defaults(func=command_package_audit)

    clean_package = sub.add_parser("clean-package", help="Remove cache/build/generated clutter from a GPTOOL tree. Dry-run by default.")
    clean_package.add_argument("root", nargs="?", default=str(ROOT))
    clean_package.add_argument("--apply", action="store_true", help="Actually remove candidates. Omit for a dry run.")
    clean_package.add_argument("--include-examples", action="store_true", help="Keep examples in this tree.")
    clean_package.add_argument("--include-generated-logs", action="store_true", help="Keep generated logs/reports in this tree.")
    clean_package.add_argument("--json", action="store_true")
    clean_package.add_argument("--output")
    clean_package.set_defaults(func=command_clean_package)

    lean_zip = sub.add_parser("package-lean-zip", help="Create a small source zip without optional examples, caches, or generated run output.")
    lean_zip.add_argument("output_zip")
    lean_zip.add_argument("--source-root", default=str(ROOT))
    lean_zip.add_argument("--include-examples", action="store_true")
    lean_zip.add_argument("--include-generated-logs", action="store_true")
    lean_zip.add_argument("--include-pycache", action="store_true")
    lean_zip.add_argument("--json", action="store_true")
    lean_zip.add_argument("--output", help="Optional JSON report path for the zip operation.")
    lean_zip.set_defaults(func=command_package_lean_zip)

    scan = sub.add_parser("scan", help="Scan a project tree.")
    scan.add_argument("project")
    scan.add_argument("--max-files", type=int, default=5000)
    scan.add_argument("--json", action="store_true")
    scan.add_argument("--output")
    scan.set_defaults(func=command_scan)

    validate = sub.add_parser("validate", help="Run the one-command validation pass.")
    add_validation_args(validate, "one-command validation pass")
    validate.set_defaults(func=command_validate)

    full = sub.add_parser("full-pass", help="Alias for validate with pass-oriented wording.")
    add_validation_args(full, "full validation pass")
    full.set_defaults(func=command_validate)


    plan_game = sub.add_parser("plan-game", help="Turn a natural-language game idea into editable Panda3D template settings.")
    plan_game.add_argument("project", help="Project/output root used for default reports path.")
    plan_game.add_argument("--profile", default="panda3d")
    plan_game.add_argument("--command", default="")
    plan_game.add_argument("--command-file")
    plan_game.add_argument("--output", help="Where to write game_settings.json. Defaults to <project>/reports/game_settings.json.")
    plan_game.add_argument("--json", action="store_true")
    plan_game.set_defaults(func=command_plan_game)

    gen_template = sub.add_parser("generate-template", help="Generate a Panda3D-ready project template from game settings JSON.")
    gen_template.add_argument("output_dir")
    gen_template.add_argument("--settings", required=True, help="game_settings.json produced by plan-game.")
    gen_template.add_argument("--force", action="store_true", help="Overwrite files in the output directory.")
    gen_template.add_argument("--report", help="Optional generation result report path.")
    gen_template.add_argument("--json", action="store_true")
    gen_template.set_defaults(func=command_generate_template)

    gen_game = sub.add_parser("generate-game", help="One command: natural-language command > settings > Panda3D-ready game template.")
    gen_game.add_argument("output_dir")
    gen_game.add_argument("--profile", default="panda3d")
    gen_game.add_argument("--command", default="")
    gen_game.add_argument("--command-file")
    gen_game.add_argument("--force", action="store_true", help="Overwrite files in the output directory.")
    gen_game.add_argument("--json", action="store_true")
    gen_game.set_defaults(func=command_generate_game)

    human_scan = sub.add_parser("scan-human-assets", help="Scan a folder for Panda3D-compatible rigged human mesh candidates.")
    human_scan.add_argument("search_root", nargs="?", default=str(ROOT.parent), help="Folder to scan. Defaults to the folder containing GPTOOL.")
    human_scan.add_argument("--max-files", type=int, default=12000)
    human_scan.add_argument("--min-score", type=int, default=25)
    human_scan.add_argument("--prefer", nargs="*", default=None, help="Ranking tokens to prefer, such as female survivor.")
    human_scan.add_argument("--require", nargs="*", default=None, help="Only include candidates whose path contains at least one token.")
    human_scan.add_argument("--rigged-only", action="store_true", help="Only include candidates with detected skin/rig data.")
    human_scan.add_argument("--json", action="store_true")
    human_scan.add_argument("--output")
    human_scan.set_defaults(func=command_scan_human_assets)

    human_import = sub.add_parser("import-human-assets", help="Copy selected rigged human mesh candidates into a generated Panda3D project.")
    human_import.add_argument("project", help="Generated Panda3D project root.")
    human_import.add_argument("--search-root", help="Folder to scan. Defaults to the folder containing GPTOOL.")
    human_import.add_argument("--limit", type=int, default=4, help="Maximum base human meshes to import.")
    human_import.add_argument("--animation-limit", type=int, default=10, help="Maximum optional animation clips to import.")
    human_import.add_argument("--export-formats", nargs="*", default=["glb", "obj", "fbx"], help="Formats to write under assets/characters/humans/exports. Supported: glb obj fbx.")
    human_import.add_argument("--prefer", nargs="*", default=None, help="Ranking tokens to prefer, such as female survivor.")
    human_import.add_argument("--require", nargs="*", default=None, help="Only include candidates whose path contains at least one token.")
    human_import.add_argument("--rigged-only", action="store_true", help="Only import base meshes with detected skin/rig data.")
    human_import.add_argument("--clean", action="store_true", help="Clear only assets/characters/humans before importing.")
    human_import.add_argument("--include-large", action="store_true", help="Allow source assets larger than 96 MiB.")
    human_import.add_argument("--force", action="store_true", help="Overwrite copied assets and reports when paths collide.")
    human_import.add_argument("--no-settings-update", action="store_true", help="Do not update settings/game_settings.json.")
    human_import.add_argument("--output", help="Import report path. Defaults to <project>/reports/human_asset_import.json.")
    human_import.add_argument("--json", action="store_true")
    human_import.set_defaults(func=command_import_human_assets)

    panda_xr = sub.add_parser("panda-xr-proof", help="Run the isolated Panda XR VR builder extension proof.")
    panda_xr.add_argument("--output", default=str(ROOT / "reports" / "panda_xr_vr_builder_proof"), help="Output folder for proof manifest, exports, and proof_result.json.")
    panda_xr.add_argument("--json", action="store_true")
    panda_xr.set_defaults(func=command_panda_xr_proof)

    panda_xr_export = sub.add_parser("panda-xr-export", help="Export a Panda XR VR builder manifest to OBJ, glTF, GLB, and metadata.")
    panda_xr_export.add_argument("manifest")
    panda_xr_export.add_argument("--output", required=True, help="Output folder for exported scene files.")
    panda_xr_export.add_argument("--json", action="store_true")
    panda_xr_export.set_defaults(func=command_panda_xr_export)

    panda_xr_quality = sub.add_parser("panda-xr-quality", help="Validate a Panda XR VR builder manifest for references, geometry, behaviors, materials, and VR performance budgets.")
    panda_xr_quality.add_argument("manifest")
    panda_xr_quality.add_argument("--output", help="Optional JSON quality report path.")
    panda_xr_quality.add_argument("--json", action="store_true")
    panda_xr_quality.set_defaults(func=command_panda_xr_quality)

    panda_xr_visual = sub.add_parser("panda-xr-visual-proof", help="Run a desktop-safe VR simulation draw pass and capture a 16:9 screenshot.")
    panda_xr_visual.add_argument("--output", default=str(ROOT / "reports" / "panda_xr_vr_visual_proof"), help="Output folder for visual proof screenshot, manifest, exports, and visual_proof_report.json.")
    panda_xr_visual.add_argument("--width", type=int, default=1600)
    panda_xr_visual.add_argument("--height", type=int, default=900)
    panda_xr_visual.add_argument("--seconds", type=float, default=3.0)
    panda_xr_visual.add_argument("--backend", choices=("auto", "panda3d", "software"), default="auto")
    panda_xr_visual.add_argument("--json", action="store_true")
    panda_xr_visual.set_defaults(func=command_panda_xr_visual_proof)

    plan = sub.add_parser("plan-command", help="Turn a natural-language game request into an AI work order.")
    plan.add_argument("project")
    plan.add_argument("--profile", default="generic_python")
    plan.add_argument("--command", default="")
    plan.add_argument("--command-file")
    plan.add_argument("--output")
    plan.add_argument("--json", action="store_true")
    plan.set_defaults(func=command_plan_command)

    verify = sub.add_parser("verify-command", help="Verify a project/report against an AI work order.")
    verify.add_argument("project")
    verify.add_argument("--work-order", required=True)
    verify.add_argument("--report", help="Optional latest_report.json from full-pass.")
    verify.add_argument("--changed-files", nargs="*", default=None)
    verify.add_argument("--strict-static", action="store_true")
    verify.add_argument("--max-files", type=int, default=5000)
    verify.add_argument("--output")
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=command_verify_command)

    screenshot = sub.add_parser("screenshot-review", help="Review a screenshot with bridge image heuristics.")
    screenshot.add_argument("image")
    screenshot.add_argument("--layout-profile", default="gameplay")
    screenshot.add_argument("--min-score", type=float, default=7.3)
    screenshot.add_argument("--output")
    screenshot.set_defaults(func=command_screenshot_review)

    regression = sub.add_parser("regression", help="Compare a candidate/current tree against a baseline tree.")
    regression.add_argument("current")
    regression.add_argument("baseline")
    regression.add_argument("--allow", nargs="*", default=None)
    regression.add_argument("--json", action="store_true")
    regression.add_argument("--output")
    regression.set_defaults(func=command_regression)

    doctor = sub.add_parser("panda3d-doctor", help="Probe Panda3D readiness and discover likely project entry points.")
    doctor.add_argument("project")
    doctor.add_argument("--entry")
    doctor.add_argument("--max-files", type=int, default=5000)
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--output")
    doctor.set_defaults(func=command_panda3d_doctor)

    runtimes = sub.add_parser("panda3d-runtimes", help="Resolve which Panda3D runtime provider the bridge will use.")
    runtimes.add_argument("project")
    runtimes.add_argument("--runtime", default="auto", choices=["auto", "system", "system_python", "portable", "portable_python", "packaged", "packaged-exe", "packaged_exe", "mock", "mock_display"])
    runtimes.add_argument("--runtime-path")
    runtimes.add_argument("--exe")
    runtimes.add_argument("--smoke-command")
    runtimes.add_argument("--json", action="store_true")
    runtimes.add_argument("--output")
    runtimes.set_defaults(func=command_panda3d_runtimes)

    smoke = sub.add_parser("panda3d-smoke", help="Launch a Panda3D project through the runtime smoke adapter.")
    add_panda_smoke_args(smoke)
    smoke.set_defaults(func=command_panda3d_smoke)

    report = sub.add_parser("report", help="Render a JSON report as Markdown text.")
    report.add_argument("report")
    report.set_defaults(func=command_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit as exc:
        raw = exc.code
        code = raw if isinstance(raw, int) else (0 if raw is None else 1)
    raise SystemExit(int(code))
