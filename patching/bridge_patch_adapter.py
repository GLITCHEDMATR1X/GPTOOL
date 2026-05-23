#!/usr/bin/env python3
"""Bridge command adapter for GPTOOL AI Patch Gate.

This module is intentionally small: bridge.py can import add_patch_gate_commands
and the commands delegate to the standalone patching scripts.  That keeps the
patch gate usable even if bridge.py is not installed/modified yet.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

PATCHING_DIR = Path(__file__).resolve().parent


def _run_python(script: str, args: list[str]) -> int:
    cmd = [sys.executable, str(PATCHING_DIR / script), *args]
    return subprocess.call(cmd)


def command_patch_gate_menu(args: argparse.Namespace) -> int:
    return _run_python("patch_gate_menu.py", [])


def command_patch_combine(args: argparse.Namespace) -> int:
    cmd = [
        "--base", args.base,
        "--output-dir", args.output_dir,
        "--report-dir", args.report_dir,
        "--profile", args.profile,
        "--emit-file-manifest",
        "--emit-repo-handoff",
        "--repo-name", args.repo_name,
    ]
    if args.order_file:
        cmd.extend(["--order-file", args.order_file])
    for patch in args.patch or []:
        cmd.extend(["--patch", patch])
    if args.project_root_name:
        cmd.extend(["--project-root-name", args.project_root_name])
    if args.output_zip:
        cmd.extend(["--output-zip", args.output_zip])
    if args.output_patch_zip:
        cmd.extend(["--output-patch-zip", args.output_patch_zip])
    if args.output_diff:
        cmd.extend(["--output-diff", args.output_diff])
    for validator in args.validator or []:
        cmd.extend(["--validator", validator])
    if args.compileall:
        cmd.append("--compileall")
    if args.fail_on_symbol_removal:
        cmd.append("--fail-on-symbol-removal")
    if args.fail_on_diff_failure:
        cmd.append("--fail-on-diff-failure")
    return _run_python("pass_combiner.py", cmd)


def command_patch_repo_dry_run(args: argparse.Namespace) -> int:
    cmd = _repo_cmd_args(args, apply=False)
    return _run_python("repo_patch_tool.py", cmd)


def command_patch_repo_apply(args: argparse.Namespace) -> int:
    cmd = _repo_cmd_args(args, apply=True)
    return _run_python("repo_patch_tool.py", cmd)


def _repo_cmd_args(args: argparse.Namespace, *, apply: bool) -> list[str]:
    cmd = [
        "--repo-root", args.repo_root,
        "--patch-zip", args.patch_zip,
        "--profile", args.profile,
        "--report-dir", args.report_dir,
        "--emit-manifest",
        "--small-updates-to-overrides",
        "--fail-on-warning",
    ]
    if args.strip_prefix:
        cmd.extend(["--strip-prefix", args.strip_prefix])
    if args.target_prefix:
        cmd.extend(["--target-prefix", args.target_prefix])
    for validator in args.validator or []:
        cmd.extend(["--validator", validator])
    if args.profile_validators:
        cmd.append("--profile-validators")
    if apply:
        cmd.append("--apply")
    return cmd


def command_patch_rules(args: argparse.Namespace) -> int:
    from .patch_gate_rules import as_json, write_rules_report
    if args.output:
        out = write_rules_report(args.output)
        print(f"Patch gate rules written: {out}")
    else:
        print(as_json())
    return 0


def add_patch_gate_commands(sub) -> None:
    menu = sub.add_parser("patch-menu", help="Open the AI Patch Gate menu.")
    menu.set_defaults(func=command_patch_gate_menu)

    rules = sub.add_parser("patch-rules", help="Print or write GPTOOL AI Patch Gate rules/profiles.")
    rules.add_argument("--output")
    rules.set_defaults(func=command_patch_rules)

    combine = sub.add_parser("patch-combine", help="Review/combine pass zips without blind protected-file overwrites.")
    combine.add_argument("--base", required=True)
    combine.add_argument("--order-file")
    combine.add_argument("--patch", action="append")
    combine.add_argument("--profile", default="holocore")
    combine.add_argument("--project-root-name")
    combine.add_argument("--output-dir", default="patch_gate_combined")
    combine.add_argument("--output-zip")
    combine.add_argument("--output-patch-zip")
    combine.add_argument("--output-diff")
    combine.add_argument("--report-dir", default="patch_gate_reports")
    combine.add_argument("--repo-name", default="local")
    combine.add_argument("--validator", action="append")
    combine.add_argument("--compileall", action="store_true")
    combine.add_argument("--fail-on-symbol-removal", action="store_true")
    combine.add_argument("--fail-on-diff-failure", action="store_true")
    combine.set_defaults(func=command_patch_combine)

    dry = sub.add_parser("patch-repo-dry-run", help="Dry-run a patch-only zip into a target repo/app folder.")
    _add_repo_args(dry)
    dry.set_defaults(func=command_patch_repo_dry_run)

    apply = sub.add_parser("patch-repo-apply", help="Apply an approved patch-only zip into a target repo/app folder.")
    _add_repo_args(apply)
    apply.set_defaults(func=command_patch_repo_apply)


def _add_repo_args(parser) -> None:
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--patch-zip", required=True)
    parser.add_argument("--strip-prefix")
    parser.add_argument("--target-prefix")
    parser.add_argument("--profile", default="gx-prototype-lab")
    parser.add_argument("--report-dir", default="repo_patch_reports")
    parser.add_argument("--validator", action="append")
    parser.add_argument("--profile-validators", action="store_true")
