#!/usr/bin/env python3
"""Repo-safe patch-only zip dry-run/apply helper.

Version: 5 companion for Safe Pass Combiner.

This script takes a patch-only zip produced by pass_combiner.py and maps it into
an existing repository checkout without dragging a full project tree into the
repo.  It is meant for workflows like:

  HoloCore patch zip path:  HoloCore/main.py
  GX repo target path:     data/HoloVerse/HoloCore/main.py

Default behavior is dry-run.  Use --apply to write files.  Existing protected
files are never blindly overwritten when the incoming file looks partial or when
--small-updates-to-overrides is enabled.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from typing import Iterable

# Reuse core safety helpers from the combiner when this script lives beside it.
try:
    from pass_combiner import (
        BUILTIN_PROFILES,
        DEFAULT_PROTECTED_PATTERNS,
        decode_text,
        encode_text,
        is_junk_path,
        python_additive_merge,
        safe_extract_zip,
        sha256_bytes,
        suspicious_shrink,
        run_process,
    )
except Exception as exc:  # pragma: no cover - startup error is user-facing
    raise SystemExit(f"Could not import pass_combiner.py helpers beside repo_patch_tool.py: {exc}")

PROTECTED_DEFAULT_MIN_SHRINK_BYTES = 2048
PROTECTED_DEFAULT_SHRINK_RATIO = 0.82
TEXT_SUFFIXES = {".py", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".txt", ".md", ".ps1", ".bat", ".spec", ".pyw", ".gitignore"}

GX_DUPLICATE_ROOT_BANS = {
    "assets",
    "data",
    "logs",
    "crash_reports",
    "dist",
    "build",
    "__pycache__",
}


@dataclass
class RepoPatchAction:
    source_path: str
    target_path: str
    action: str
    detail: str = ""
    old_size: int | None = None
    new_size: int | None = None
    old_sha256: str | None = None
    new_sha256: str | None = None


def _norm_rel(path: str) -> str:
    path = str(path or "").replace("\\", "/").strip("/")
    parts = [p for p in path.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise ValueError(f"Unsafe relative path: {path!r}")
    return "/".join(parts)


def _strip_prefix(path: str, prefix: str | None) -> str | None:
    path = _norm_rel(path)
    prefix = _norm_rel(prefix or "")
    if not prefix:
        return path
    if path == prefix:
        return ""
    if path.startswith(prefix + "/"):
        return path[len(prefix) + 1:]
    return None


def _target_path(source_path: str, strip_prefix: str | None, target_prefix: str | None) -> str | None:
    stripped = _strip_prefix(source_path, strip_prefix)
    if stripped is None or not stripped:
        return None
    target_prefix = _norm_rel(target_prefix or "")
    return _norm_rel(f"{target_prefix}/{stripped}" if target_prefix else stripped)


def zip_entries(zip_path: Path) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if not name or name.endswith("/") or is_junk_path(name):
                continue
            rel = _norm_rel(name)
            if is_junk_path(rel):
                continue
            entries[rel] = zf.read(info)
    return entries


def profile_patterns(profile: str, extra_patterns: Iterable[str]) -> list[str]:
    pats: list[str] = []
    pats.extend(DEFAULT_PROTECTED_PATTERNS)
    prof = BUILTIN_PROFILES.get(profile, {})
    pats.extend(prof.get("protected_patterns", []))
    pats.extend(extra_patterns or [])
    # Deduplicate while preserving order.
    out: list[str] = []
    seen: set[str] = set()
    for pat in pats:
        p = str(pat).replace("\\", "/")
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def is_protected(target_rel: str, patterns: Iterable[str]) -> bool:
    target_rel = target_rel.replace("\\", "/")
    for pat in patterns:
        pat = pat.replace("\\", "/")
        if fnmatch.fnmatch(target_rel, pat) or fnmatch.fnmatch(Path(target_rel).name, pat):
            return True
    return False


def is_small_update(current: bytes, incoming: bytes, max_bytes: int) -> bool:
    if len(incoming) > max_bytes:
        return False
    if len(current) == len(incoming) and sha256_bytes(current) == sha256_bytes(incoming):
        return False
    return True


def write_override(overrides_dir: Path, pass_name: str, target_rel: str, data: bytes) -> Path:
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in pass_name)[:120] or "patch"
    out = overrides_dir / safe_name / target_rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


def write_manifest(repo_root: Path, output: Path) -> None:
    rows = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root).as_posix()
        if is_junk_path(rel) or rel.startswith("_pass_overrides/"):
            continue
        data = path.read_bytes()
        rows.append({"path": rel, "size": len(data), "sha256": sha256_bytes(data)})
    output.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def validate_mapping(entries: dict[str, bytes], strip_prefix: str | None, target_prefix: str | None, profile: str) -> list[str]:
    problems: list[str] = []
    if profile == "gx-prototype-lab" and strip_prefix and not target_prefix:
        problems.append("GX profile refuses to strip a project folder into the repo root. Use --target-prefix such as data/HoloVerse/HoloCore.")
    mapped: list[str] = []
    for src in entries:
        tgt = _target_path(src, strip_prefix, target_prefix)
        if tgt:
            mapped.append(tgt)
    if not mapped:
        problems.append("No patch entries mapped into the repo. Check --strip-prefix and --target-prefix.")
    if profile == "gx-prototype-lab" and not target_prefix:
        # In GX, a patch-only zip with HoloCore/assets should not land at repo root.
        for tgt in mapped:
            first = tgt.split("/", 1)[0]
            if first in GX_DUPLICATE_ROOT_BANS:
                problems.append(
                    f"GX profile rejects root-level {first!r} from patch target {tgt!r}. Use --target-prefix like data/HoloVerse/HoloCore."
                )
                break
    return problems


def apply_or_plan(
    *,
    repo_root: Path,
    patch_zip: Path,
    strip_prefix: str | None,
    target_prefix: str | None,
    report_dir: Path,
    profile: str,
    apply: bool,
    protected_patterns: list[str],
    small_updates_to_overrides: bool,
    small_update_max_bytes: int,
    min_shrink_bytes: int,
    shrink_ratio: float,
    try_python_merge: bool,
    allow_new_files: bool,
) -> tuple[list[RepoPatchAction], list[str], list[str]]:
    entries = zip_entries(patch_zip)
    errors = validate_mapping(entries, strip_prefix, target_prefix, profile)
    warnings: list[str] = []
    actions: list[RepoPatchAction] = []
    overrides_dir = repo_root / "_pass_overrides"
    pass_name = patch_zip.stem

    for src, incoming in sorted(entries.items()):
        target_rel = _target_path(src, strip_prefix, target_prefix)
        if not target_rel:
            actions.append(RepoPatchAction(src, "", "skipped_unmapped", "source did not match strip prefix"))
            continue
        if is_junk_path(target_rel):
            actions.append(RepoPatchAction(src, target_rel, "skipped_junk"))
            continue
        target = repo_root / target_rel
        if not str(target.resolve()).startswith(str(repo_root.resolve())):
            errors.append(f"Unsafe target outside repo: {target_rel}")
            continue
        protected = is_protected(target_rel, protected_patterns)
        incoming_sha = sha256_bytes(incoming)
        if not target.exists():
            if not allow_new_files:
                out = write_override(overrides_dir, pass_name, target_rel, incoming) if apply else overrides_dir / pass_name / target_rel
                actions.append(RepoPatchAction(src, target_rel, "override_new_file", f"new files disabled; staged to {out}", new_size=len(incoming), new_sha256=incoming_sha))
                warnings.append(f"new file staged for review: {target_rel}")
                continue
            if apply:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(incoming)
            actions.append(RepoPatchAction(src, target_rel, "add", "new file", new_size=len(incoming), new_sha256=incoming_sha))
            continue

        current = target.read_bytes()
        current_sha = sha256_bytes(current)
        if current_sha == incoming_sha:
            actions.append(RepoPatchAction(src, target_rel, "unchanged", old_size=len(current), new_size=len(incoming), old_sha256=current_sha, new_sha256=incoming_sha))
            continue

        if small_updates_to_overrides and is_small_update(current, incoming, small_update_max_bytes):
            out = write_override(overrides_dir, pass_name, target_rel, incoming) if apply else overrides_dir / pass_name / target_rel
            actions.append(RepoPatchAction(src, target_rel, "override_small_update", f"small update staged to {out}", old_size=len(current), new_size=len(incoming), old_sha256=current_sha, new_sha256=incoming_sha))
            warnings.append(f"small update staged for review: {target_rel}")
            continue

        if protected and suspicious_shrink(current, incoming, target_rel, min_shrink_bytes, shrink_ratio):
            if try_python_merge and target.suffix.lower() == ".py":
                merged, detail, unresolved = python_additive_merge(current, incoming, target_rel)
                if merged is not None and not unresolved and sha256_bytes(merged) != current_sha:
                    if apply:
                        target.write_bytes(merged)
                    actions.append(RepoPatchAction(src, target_rel, "merge_python_defs", detail, old_size=len(current), new_size=len(merged), old_sha256=current_sha, new_sha256=sha256_bytes(merged)))
                    continue
            out = write_override(overrides_dir, pass_name, target_rel, incoming) if apply else overrides_dir / pass_name / target_rel
            actions.append(RepoPatchAction(src, target_rel, "override_blocked_shrink", f"protected suspicious shrink staged to {out}", old_size=len(current), new_size=len(incoming), old_sha256=current_sha, new_sha256=incoming_sha))
            warnings.append(f"protected suspicious shrink staged for review: {target_rel}")
            continue

        if protected and try_python_merge and target.suffix.lower() == ".py":
            # For protected Python, prefer an additive definition merge.  If it
            # cannot prove a safe merge, stage to override instead of replacing.
            merged, detail, unresolved = python_additive_merge(current, incoming, target_rel)
            if merged is not None and not unresolved and sha256_bytes(merged) != current_sha:
                if apply:
                    target.write_bytes(merged)
                actions.append(RepoPatchAction(src, target_rel, "merge_python_defs", detail, old_size=len(current), new_size=len(merged), old_sha256=current_sha, new_sha256=sha256_bytes(merged)))
            else:
                out = write_override(overrides_dir, pass_name, target_rel, incoming) if apply else overrides_dir / pass_name / target_rel
                actions.append(RepoPatchAction(src, target_rel, "override_protected_python", f"protected Python update staged to {out}; {detail}", old_size=len(current), new_size=len(incoming), old_sha256=current_sha, new_sha256=incoming_sha))
                warnings.append(f"protected Python staged for review: {target_rel}")
            continue

        if protected:
            # Protected non-Python is allowed only when it is not a shrink and
            # not a small-update override case.  This still gets an explicit log.
            detail = "protected non-Python replaced after guard checks"
        else:
            detail = "replaced"
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(incoming)
        actions.append(RepoPatchAction(src, target_rel, "replace", detail, old_size=len(current), new_size=len(incoming), old_sha256=current_sha, new_sha256=incoming_sha))

    return actions, warnings, errors


def run_validators(repo_root: Path, validators: list[str], timeout: int) -> list[dict]:
    results = []
    for cmd in validators:
        proc = run_process(cmd, cwd=repo_root, shell=True, timeout_seconds=timeout)
        results.append({
            "command": cmd,
            "returncode": proc.returncode,
            "output": (proc.stdout or "")[-4000:],
        })
    return results


def write_reports(report_dir: Path, actions: list[RepoPatchAction], warnings: list[str], errors: list[str], validators: list[dict], args: argparse.Namespace) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 5,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "repo_root": str(Path(args.repo_root).resolve()),
        "patch_zip": str(Path(args.patch_zip).resolve()),
        "strip_prefix": args.strip_prefix,
        "target_prefix": args.target_prefix,
        "profile": args.profile,
        "applied": bool(args.apply),
        "warnings": warnings,
        "errors": errors,
        "validators": validators,
        "actions": [asdict(a) for a in actions],
    }
    (report_dir / "repo_patch_plan.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# Repo Patch Plan",
        "",
        f"Generated: {payload['generated_at']}",
        f"Profile: `{args.profile}`",
        f"Patch zip: `{args.patch_zip}`",
        f"Repo root: `{Path(args.repo_root).resolve()}`",
        f"Mapping: `{args.strip_prefix or ''}` -> `{args.target_prefix or ''}`",
        f"Mode: `{'apply' if args.apply else 'dry-run'}`",
        "",
    ]
    if errors:
        lines += ["## Errors", ""] + [f"- {e}" for e in errors] + [""]
    if warnings:
        lines += ["## Review Warnings", ""] + [f"- {w}" for w in warnings] + [""]
    if validators:
        lines += ["## Validators", ""]
        for v in validators:
            status = "PASS" if v["returncode"] == 0 else "FAIL"
            lines.append(f"- `{status}` `{v['command']}`")
        lines.append("")
    counts = {}
    for a in actions:
        counts[a.action] = counts.get(a.action, 0) + 1
    lines += ["## Action Counts", ""] + [f"- `{k}`: {v}" for k, v in sorted(counts.items())] + [""]
    lines += ["## Actions", "", "| Action | Target | Source | Detail |", "|---|---|---|---|"]
    for a in actions:
        detail = a.detail.replace("|", "\\|")[:300]
        lines.append(f"| `{a.action}` | `{a.target_path}` | `{a.source_path}` | {detail} |")
    (report_dir / "repo_patch_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run or apply patch-only zip into a repository checkout safely.")
    parser.add_argument("--repo-root", required=True, help="Existing repository checkout root.")
    parser.add_argument("--patch-zip", required=True, help="Patch-only zip to map/apply.")
    parser.add_argument("--strip-prefix", default="", help="Patch zip prefix to strip, e.g. HoloCore.")
    parser.add_argument("--target-prefix", default="", help="Repo target prefix, e.g. data/HoloVerse/HoloCore.")
    parser.add_argument("--profile", default="generic", choices=sorted(BUILTIN_PROFILES.keys()), help="Safety profile.")
    parser.add_argument("--protected-pattern", action="append", default=[], help="Additional protected glob pattern after target mapping.")
    parser.add_argument("--report-dir", default="repo_patch_reports", help="Where to write repo_patch_plan.md/json.")
    parser.add_argument("--apply", action="store_true", help="Actually write changes. Default is dry-run.")
    parser.add_argument("--allow-new-files", action="store_true", default=True, help="Allow adding new files. Default on.")
    parser.add_argument("--no-new-files", dest="allow_new_files", action="store_false", help="Stage new files into overrides instead of adding.")
    parser.add_argument("--small-updates-to-overrides", action="store_true", help="Stage small existing-file updates to _pass_overrides instead of replacing.")
    parser.add_argument("--small-update-max-bytes", type=int, default=4096, help="Max incoming size considered a small update.")
    parser.add_argument("--min-shrink-bytes", type=int, default=PROTECTED_DEFAULT_MIN_SHRINK_BYTES)
    parser.add_argument("--shrink-ratio", type=float, default=PROTECTED_DEFAULT_SHRINK_RATIO)
    parser.add_argument("--no-python-merge", dest="try_python_merge", action="store_false", help="Do not attempt protected Python additive merge.")
    parser.set_defaults(try_python_merge=True)
    parser.add_argument("--validator", action="append", default=[], help="Validator command to run after apply/dry-run.")
    parser.add_argument("--profile-validators", action="store_true", help="Also run validators from the selected built-in profile.")
    parser.add_argument("--validator-timeout", type=int, default=120)
    parser.add_argument("--emit-manifest", action="store_true", help="Write repo_file_manifest_after.json after apply/dry-run.")
    parser.add_argument("--fail-on-warning", action="store_true", help="Return nonzero when review warnings exist.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = Path(args.repo_root).resolve()
    patch_zip = Path(args.patch_zip).resolve()
    report_dir = Path(args.report_dir).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise SystemExit(f"Repo root not found: {repo_root}")
    if not patch_zip.exists() or patch_zip.suffix.lower() != ".zip":
        raise SystemExit(f"Patch zip not found or not a zip: {patch_zip}")

    pats = profile_patterns(args.profile, args.protected_pattern)
    actions, warnings, errors = apply_or_plan(
        repo_root=repo_root,
        patch_zip=patch_zip,
        strip_prefix=args.strip_prefix,
        target_prefix=args.target_prefix,
        report_dir=report_dir,
        profile=args.profile,
        apply=args.apply,
        protected_patterns=pats,
        small_updates_to_overrides=args.small_updates_to_overrides,
        small_update_max_bytes=args.small_update_max_bytes,
        min_shrink_bytes=args.min_shrink_bytes,
        shrink_ratio=args.shrink_ratio,
        try_python_merge=args.try_python_merge,
        allow_new_files=args.allow_new_files,
    )
    validators: list[dict] = []
    validator_cmds = []
    if args.profile_validators:
        validator_cmds.extend(BUILTIN_PROFILES.get(args.profile, {}).get("validators", []))
    validator_cmds.extend(args.validator or [])
    if validator_cmds:
        validators = run_validators(repo_root, validator_cmds, args.validator_timeout)
        for result in validators:
            if result["returncode"] != 0:
                errors.append(f"validator failed: {result['command']}")
    if args.emit_manifest:
        report_dir.mkdir(parents=True, exist_ok=True)
        write_manifest(repo_root, report_dir / "repo_file_manifest_after.json")
    write_reports(report_dir, actions, warnings, errors, validators, args)

    if errors:
        print(f"Repo patch finished with errors. See {report_dir / 'repo_patch_plan.md'}")
        return 2
    if warnings:
        print(f"Repo patch finished with review warnings. See {report_dir / 'repo_patch_plan.md'}")
        return 1 if args.fail_on_warning else 0
    print(f"Repo patch {'applied' if args.apply else 'dry-run'} clean. See {report_dir / 'repo_patch_plan.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
