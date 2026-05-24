# -*- mode: python ; coding: utf-8 -*-
"""
py_runner.spec

Minimal HoloVerse portable-runner dependency fix.
This keeps the existing portable onedir py_runner design, but forces the
frozen runner to include modules used by scripts it launches dynamically.

Reason: HoloVerse is run through runpy.run_path(), so PyInstaller cannot see
imports inside data/HoloVerse/main.py during py_runner analysis.  Without
hiddenimports, stdlib modules such as wave can be missing at runtime.
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).resolve()

datas = []
binaries = []
hiddenimports = []

# Standard-library modules that HoloVerse / Panda3D side scripts commonly load
# after py_runner is already frozen.  Explicitly include wave: that is the
# current runtime failure from the EXE log.
hiddenimports += [
    "wave",
    "chunk",
    "audioop",
    "aifc",
    "sunau",
    "sndhdr",
    "contextlib",
    "struct",
    "colorsys",
    "fractions",
    "decimal",
    "statistics",
    "pickle",
    "gzip",
    "zipfile",
    "csv",
    "configparser",
    "xml",
    "xml.etree.ElementTree",
    "urllib",
    "urllib.request",
    "urllib.parse",
    "http",
    "http.client",
    "socket",
    "ssl",
    "ctypes",
    "ctypes.wintypes",
    "logging",
    "inspect",
    "importlib",
    "importlib.util",
    "importlib.resources",
    "pkgutil",
    "dataclasses",
    "typing",
    "enum",
    "queue",
    "threading",
    "subprocess",
    "multiprocessing",
    "shutil",
    "tempfile",
    "platform",
    "traceback",
    "textwrap",
    "_tkinter",
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.simpledialog",
    "tkinter.font",
    "tkinter.colorchooser",
]

# Game/runtime packages used by GX prototypes and HoloVerse.  Missing optional
# packages are ignored so the old builder still works with the installed set.
packages = (
    "panda3d",
    "direct",
    "pygame",
    "numpy",
    "PIL",
    "mss",
    "panda3d_gltf",
    "simplepbr",
    "pydub",
    "cv2",
    "tkinterdnd2",
    "reportlab",
    "trimesh",
    "pyttsx3",
)

for pkg in packages:
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass
    try:
        pkg_datas, pkg_bins, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_bins
        hiddenimports += pkg_hidden
    except Exception:
        pass

hiddenimports += [
    "panda3d.core",
    "panda3d.ai",
    "panda3d.physics",
    "panda3d.egg",
    "direct.showbase.ShowBase",
    "direct.showbase.DirectObject",
    "direct.gui.DirectGui",
    "direct.gui.OnscreenText",
    "direct.gui.OnscreenImage",
    "direct.task.Task",
    "direct.interval.IntervalGlobal",
    "direct.actor.Actor",
    "direct.controls.InputStateGlobal",
    "panda3d_gltf",
    "simplepbr",
]

hiddenimports = sorted(set(hiddenimports))

a = Analysis(
    ["py_runner.py"],
    pathex=[str(root), str(root / "data"), str(root / "data" / "HoloVerse")],
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
    name="py_runner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="py_runner",
)
