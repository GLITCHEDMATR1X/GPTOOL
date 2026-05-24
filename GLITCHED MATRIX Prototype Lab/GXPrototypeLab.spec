# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).resolve()

datas = []
binaries = []
hiddenimports = []

JUNK_DIR_NAMES = {
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env", "build", "dist",
    "crash_reports", "screenshots",
}
JUNK_FILE_SUFFIXES = {".pyc", ".pyo", ".tmp", ".temp", ".bak", ".orig", ".log"}
JUNK_FILE_NAMES = {
    "latest.log", "latest_crash.txt", "latest_game_log.txt", "latest_runner_crash.txt",
    "bridge_exit_cleanup_auto.json", "bridge_exit_cleanup_auto.png",
    "mode_gateway_audit.json", "mode_gateway_history.json", "mode_gateway_self_test.json",
    "self_test_report.json", "runtime_integration_smoke_report.json",
    "world_authority_smoke.png", "world_authority_smoke_report.json",
}


def _skip_file(path: Path) -> bool:
    name = path.name.lower()
    if path.suffix.lower() in JUNK_FILE_SUFFIXES:
        return True
    if name in JUNK_FILE_NAMES:
        return True
    if name.endswith("_smoke.png") or name.endswith("_smoke_report.json"):
        return True
    return False


def _skip_dir(path: Path) -> bool:
    name = path.name.lower()
    if name in JUNK_DIR_NAMES:
        return True
    # Keep only HoloVerse/logs/ROADMAP_STATUS.md by skipping logs as a tree and
    # explicitly re-adding that file below.
    if name == "logs":
        return True
    return False


def add_clean_tree(src: Path, dest_prefix: str) -> None:
    if not src.exists():
        return
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if any(part.lower() in JUNK_DIR_NAMES or part.lower() == "logs" for part in rel.parts[:-1]):
            continue
        if item.is_dir():
            continue
        if any(_skip_dir(parent) for parent in item.parents if src in parent.parents or parent == src):
            continue
        if _skip_file(item):
            continue
        datas.append((str(item), str(Path(dest_prefix) / rel.parent)))
    roadmap = src / "HoloVerse" / "logs" / "ROADMAP_STATUS.md"
    if roadmap.exists():
        datas.append((str(roadmap), str(Path(dest_prefix) / "HoloVerse" / "logs")))


# The launcher can execute child scripts through py_runner/runpy, so PyInstaller
# cannot infer every dependency from static imports in this file. Keep the child
# runner package coverage mirrored here for the fallback GXPrototypeLab.exe
# script-runner route. Missing optional packages are ignored by design.
for pkg in (
    'pyttsx3', 'pygame', 'PIL', 'tkinterdnd2', 'panda3d', 'direct',
    'numpy', 'mss', 'panda3d_gltf', 'simplepbr', 'pydub', 'reportlab',
    'trimesh', 'cv2'
):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass
    try:
        tmp = collect_all(pkg)
        datas += tmp[0]
        binaries += tmp[1]
        hiddenimports += tmp[2]
    except Exception:
        pass

hiddenimports += [
    '_tkinter', 'tkinter', 'tkinter.ttk', 'tkinter.filedialog',
    'tkinter.messagebox', 'tkinter.simpledialog', 'tkinter.font',
    'tkinter.colorchooser',
    'panda3d.core', 'panda3d.ai', 'panda3d.physics', 'panda3d.egg',
    'direct.showbase.ShowBase', 'direct.showbase.DirectObject',
    'direct.gui.DirectGui', 'direct.gui.OnscreenText', 'direct.gui.OnscreenImage',
    'direct.task.Task', 'direct.interval.IntervalGlobal', 'direct.actor.Actor',
    'direct.controls.InputStateGlobal', 'panda3d_gltf', 'simplepbr',
]
hiddenimports = sorted(set(hiddenimports))

for rel in ('assets', 'data'):
    add_clean_tree(root / rel, rel)

for rel in (
    'desktop_settings.json',
    'folder_list.txt',
    'launcher_logo.png',
    'install_requirements.bat',
    'patch_notes_workstation.py',
    'README_BUILD_EXE.md',
):
    src = root / rel
    if src.exists():
        datas.append((str(src), '.'))

a = Analysis(
    ['GXPrototypeLab_boot.py'],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GXPrototypeLab',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(root / 'assets' / 'icons' / 'GXPrototypeLab.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GXPrototypeLab',
)
