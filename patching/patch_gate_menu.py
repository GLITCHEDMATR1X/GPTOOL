#!/usr/bin/env python3
"""Friendly Windows menu for GPTOOL AI Patch Gate.

Designed to be double-click safe.  It never applies patches by default.  The
first action is always review/dry-run, and APPLY mode asks for typed approval.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

TOOL_DIR = Path(__file__).resolve().parent
GPTOOL_ROOT = TOOL_DIR.parent
LOG_DIR = GPTOOL_ROOT / "patch_gate_launcher_logs"
DEFAULT_GX_REPO = Path(r"D:\Apps\GLITCHED MATRIX Prototype Lab")
DEFAULT_HOLOCORE_TARGET = "data/HoloVerse/HoloCore"


def pause(msg: str = "Press Enter to continue...") -> None:
    try:
        input("\n" + msg)
    except Exception:
        pass


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def title() -> None:
    print("=" * 76)
    print(" GPTOOL Pass 17 - AI Patch Gate")
    print("=" * 76)
    print("Rule: patches do not overwrite protected files; they are reviewed, combined, staged, then approved.")
    print("")


def run_cmd(args: list[str], cwd: Path = GPTOOL_ROOT) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"patch_gate_{stamp}.log"
    print("\nRunning:")
    print(" ".join(f'\"{a}\"' if " " in a else a for a in args))
    print(f"\nLog: {log_path}\n")
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("COMMAND:\n" + " ".join(args) + "\n\n")
        try:
            proc = subprocess.Popen(args, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line, end="")
                log.write(line)
            rc = proc.wait()
        except Exception as exc:
            print(f"Command failed before completion: {exc}")
            log.write(f"\nCommand failed before completion: {exc}\n")
            return 1
        log.write(f"\nRETURN CODE: {rc}\n")
    print(f"\nReturn code: {rc}")
    return int(rc)


def find_zips() -> list[Path]:
    roots = [GPTOOL_ROOT, Path.cwd(), GPTOOL_ROOT.parent, TOOL_DIR]
    found: list[Path] = []
    for root in roots:
        try:
            found.extend(root.glob("*.zip"))
        except Exception:
            pass
    seen: set[str] = set()
    out: list[Path] = []
    for p in found:
        key = str(p.resolve()).lower()
        if key not in seen:
            seen.add(key)
            out.append(p.resolve())
    return sorted(out, key=lambda p: p.name.lower())


def choose_zip(prompt: str = "Choose zip") -> Path | None:
    zips = find_zips()
    if zips:
        print(prompt + ":")
        for i, p in enumerate(zips, 1):
            print(f"  {i}. {p}")
        print("  M. Manually type a path")
        choice = input("Selection [1]: ").strip() or "1"
        if choice.lower() == "m":
            raw = input("Zip path: ").strip().strip('"')
            return Path(raw).expanduser().resolve() if raw else None
        try:
            idx = int(choice)
            if 1 <= idx <= len(zips):
                return zips[idx - 1]
        except Exception:
            pass
        print("Invalid selection.")
        return None
    raw = input(prompt + " path: ").strip().strip('"')
    return Path(raw).expanduser().resolve() if raw else None


def choose_repo() -> Path | None:
    candidates: list[Path] = []
    for raw in [os.environ.get("GX_REPO_ROOT"), str(DEFAULT_GX_REPO), str(Path.cwd())]:
        if raw:
            p = Path(raw).expanduser()
            if p.exists() and p.is_dir():
                candidates.append(p.resolve())
    seen: set[str] = set()
    candidates = [p for p in candidates if not (str(p).lower() in seen or seen.add(str(p).lower()))]
    if candidates:
        print("Target repo/app folders found:")
        for i, p in enumerate(candidates, 1):
            marker = ""
            if (p / "GXPrototypeLab.py").exists() or (p / "data" / "gx_app_main.py").exists():
                marker = " [looks like GX root]"
            print(f"  {i}. {p}{marker}")
        print("  M. Manually type a path")
        choice = input("Selection [1]: ").strip() or "1"
        if choice.lower() == "m":
            raw = input("Repo/app root path: ").strip().strip('"')
            return Path(raw).expanduser().resolve() if raw else None
        try:
            idx = int(choice)
            if 1 <= idx <= len(candidates):
                return candidates[idx - 1]
        except Exception:
            pass
        print("Invalid selection.")
        return None
    raw = input("Repo/app root path: ").strip().strip('"')
    return Path(raw).expanduser().resolve() if raw else None


def infer_strip_prefix(zip_path: Path) -> str:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            tops: list[str] = []
            for info in zf.infolist():
                name = info.filename.replace("\\", "/").strip("/")
                if not name or name.endswith("/"):
                    continue
                first = name.split("/", 1)[0]
                if first not in tops:
                    tops.append(first)
            for preferred in ("HoloCore", "HoloVerse", "HoloUtopia"):
                if preferred in tops:
                    return preferred
            if len(tops) == 1:
                return tops[0]
    except Exception:
        pass
    return "HoloCore"


def profile_prompt(default: str = "holocore") -> str:
    print("Profiles: holocore, holoverse, gx-prototype-lab, holoutopia, vector-arena, panda3d-ai-game")
    raw = input(f"Profile [{default}]: ").strip()
    return raw or default


def review_combine() -> int:
    base = choose_zip("Base project zip")
    if not base:
        print("No base selected.")
        return 1
    order = input("Optional pass order .txt path, or leave blank to choose zips manually: ").strip().strip('"')
    profile = profile_prompt("holocore")
    out_dir = GPTOOL_ROOT / "patch_gate_combined"
    report_dir = GPTOOL_ROOT / "patch_gate_reports"
    out_zip = GPTOOL_ROOT / "patch_gate_combined.zip"
    out_patch = GPTOOL_ROOT / "patch_gate_PATCH_ONLY.zip"
    out_diff = GPTOOL_ROOT / "patch_gate.diff"
    cmd = [sys.executable, str(TOOL_DIR / "pass_combiner.py"), "--base", str(base), "--profile", profile, "--output-dir", str(out_dir), "--output-zip", str(out_zip), "--output-patch-zip", str(out_patch), "--output-diff", str(out_diff), "--report-dir", str(report_dir), "--compileall", "--emit-file-manifest", "--emit-repo-handoff", "--repo-name", "local"]
    if order:
        cmd.extend(["--order-file", order])
    else:
        print("Choose pass zips in the order they should be reviewed. Blank when done.")
        while True:
            p = choose_zip("Pass patch zip")
            if not p:
                break
            cmd.extend(["--patch", str(p)])
            more = input("Add another pass zip? [y/N]: ").strip().lower()
            if more != "y":
                break
    return run_cmd(cmd)


def repo_dry_run(apply: bool = False) -> int:
    patch_zip = choose_zip("Patch-only zip")
    if not patch_zip:
        print("No patch zip selected.")
        return 1
    repo = choose_repo()
    if not repo:
        print("No repo/app root selected.")
        return 1
    strip = input(f"Strip prefix [{infer_strip_prefix(patch_zip)}]: ").strip() or infer_strip_prefix(patch_zip)
    default_target = DEFAULT_HOLOCORE_TARGET if strip.lower() == "holocore" else "data/HoloVerse"
    target = input(f"Target prefix [{default_target}]: ").strip() or default_target
    profile = profile_prompt("gx-prototype-lab")
    cmd = [sys.executable, str(TOOL_DIR / "repo_patch_tool.py"), "--repo-root", str(repo), "--patch-zip", str(patch_zip), "--strip-prefix", strip, "--target-prefix", target, "--profile", profile, "--report-dir", str(GPTOOL_ROOT / "repo_patch_reports"), "--emit-manifest", "--small-updates-to-overrides", "--fail-on-warning"]
    if apply:
        print("\nAPPLY mode writes safe/approved mapped files and stages risky files under _pass_overrides.")
        confirm = input("Type APPLY to continue: ").strip()
        if confirm != "APPLY":
            print("Cancelled. No files changed.")
            return 1
        cmd.append("--apply")
    return run_cmd(cmd)


def show_report() -> None:
    candidates = []
    for folder in (GPTOOL_ROOT / "patch_gate_reports", GPTOOL_ROOT / "repo_patch_reports"):
        if folder.exists():
            candidates.extend(folder.glob("*.md"))
    if not candidates:
        print("No patch gate reports found yet.")
        return
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    print(f"Latest report: {latest}\n")
    text = latest.read_text(encoding="utf-8", errors="replace")
    print(text[:10000])
    if len(text) > 10000:
        print("\n...truncated in console. Open the report file for the full version.")


def selftests() -> int:
    scripts = ["selftest_pass_combiner.py", "selftest_pass_combiner_v4.py", "selftest_repo_patch_tool.py"]
    rc = 0
    for script in scripts:
        path = TOOL_DIR / script
        if path.exists():
            rc = run_cmd([sys.executable, str(path)], cwd=TOOL_DIR) or rc
    return rc


def install_bridge(apply: bool = False) -> int:
    cmd = [sys.executable, str(TOOL_DIR / "install_bridge_patch_gate.py"), "--bridge", str(GPTOOL_ROOT / "bridge.py")]
    if apply:
        print("This will modify bridge.py and create bridge.py.patch_gate.bak.")
        confirm = input("Type INSTALL to continue: ").strip()
        if confirm != "INSTALL":
            print("Cancelled. No files changed.")
            return 1
        cmd.append("--apply")
    return run_cmd(cmd)


def print_examples() -> None:
    print("Bridge commands after optional install:")
    print("  python bridge.py patch-menu")
    print("  python bridge.py patch-rules")
    print("  python bridge.py patch-combine --base HoloCore.zip --order-file passes.txt --profile holocore --compileall --output-patch-zip HoloCore_PATCH_ONLY.zip --output-diff HoloCore.diff")
    print("  python bridge.py patch-repo-dry-run --repo-root \"D:\\Apps\\GLITCHED MATRIX Prototype Lab\" --patch-zip HoloCore_PATCH_ONLY.zip --strip-prefix HoloCore --target-prefix data/HoloVerse/HoloCore --profile gx-prototype-lab")


def menu() -> int:
    while True:
        clear(); title()
        print("1. Review/combine pass zips into approved patch-only output")
        print("2. Dry-run patch-only zip into GX/app repo")
        print("3. APPLY approved patch-only zip into GX/app repo")
        print("4. Show latest patch gate report")
        print("5. Run patch gate self-tests")
        print("6. Dry-run bridge.py command install")
        print("7. INSTALL bridge.py commands")
        print("8. Print command examples")
        print("0. Exit")
        choice = input("\nChoose: ").strip()
        clear(); title()
        if choice == "1":
            review_combine(); pause()
        elif choice == "2":
            repo_dry_run(False); pause()
        elif choice == "3":
            repo_dry_run(True); pause()
        elif choice == "4":
            show_report(); pause()
        elif choice == "5":
            selftests(); pause()
        elif choice == "6":
            install_bridge(False); pause()
        elif choice == "7":
            install_bridge(True); pause()
        elif choice == "8":
            print_examples(); pause()
        elif choice == "0":
            return 0
        else:
            print("Invalid choice."); pause()


def main() -> int:
    try:
        return menu()
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130

if __name__ == "__main__":
    raise SystemExit(main())
