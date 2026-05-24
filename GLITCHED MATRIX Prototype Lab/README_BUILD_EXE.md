# GXPrototypeLab EXE Build Kit (Windows / PowerShell)

This build layout is for a **portable onedir launcher**.

## What it fixes

- The launcher now resolves **assets, wallpaper, icons, previews, data, and desktop settings** from one authoritative portable bundle tree.
- The frozen build no longer relies on old `MatrixOS` names.
- The launcher can scan `games/Arcade Evolution`, `games/Prototype Lab`, `games/Test Lab`, and `games/Tool Test Lab` beside the EXE.
- `folder_list.txt` is kept with the build so category hints remain available even when the upload/package omits the large games folder.
- `py_runner.exe` is built separately so launching `main.py` entries still works after freezing.

## Included build files

- `build_GXPrototypeLab.ps1`
- `GXPrototypeLab.spec`
- `py_runner.spec`
- `GXPrototypeLab_boot.py`
- `py_runner.py`

## Build

## Build requirements

This kit now expects a real `requirements.txt` beside the spec files. The PowerShell build script fails fast if that file is missing instead of silently producing a stale or Panda3D-incomplete build.

Base runtime/build packages installed from `requirements.txt`:

- pyinstaller
- pillow
- pygame
- pyttsx3
- tkinter / Tcl-Tk runtime from the selected Python install
- tkinterdnd2
- panda3d
- panda3d-gltf
- panda3d-simplepbr
- numpy
- pydub
- reportlab
- trimesh
- opencv-python

Use `-Full` only for heavier optional GUI stacks such as PyQt6 and PySide6.


Open PowerShell in the GXPrototypeLab folder and run:

```powershell
.\build_GXPrototypeLab.ps1
```

Optional switches:

```powershell
.\build_GXPrototypeLab.ps1 -Full
.\build_GXPrototypeLab.ps1 -ZipDist
.\build_GXPrototypeLab.ps1 -IncludeGames
```

## Portable layout expectations

The finished folder should contain at least:

- `GXPrototypeLab.exe`
- `py_runner\py_runner.exe`
- `_internal\assets\`
- `_internal\data\`

Do not add duplicate root-level `assets\` or `data\` folders to the Steam depot. PyInstaller owns the bundled runtime tree under `_internal`; `py_runner\` is the only separate child-runtime folder expected beside the EXE.

The large `games\` folder is **optional during EXE build** and can stay external until you assemble the final Steam depot. If `games\` is present beside the EXE, the launcher will scan it normally.

## Troubleshooting

During development, failed runs may create crash reports. The final builder removes stale crash/log folders from the Steam-ready tree before zipping.

## Panda3D

`py_runner.spec` collects `panda3d` and `direct` so Panda3D-based entries can launch from the frozen launcher.


## Spec file fix

These spec files use `SPECPATH` instead of `__file__`, because PyInstaller does not reliably define `__file__` while executing a `.spec` file. The PowerShell build script also aborts immediately if PyInstaller or pip returns a non-zero exit code, so it cannot silently zip a stale or partial `dist` folder.

- The launcher now recovers external `games` roots from recorded absolute paths in `desktop_settings.json` when the packed build omits the large `games` folder.
- The build script now copies the full `dist\py_runner` runtime folder instead of only `py_runner.exe`, so Panda3D-based child apps keep their bundled support files.


If dependency install flashes and closes while running from source, run `install_requirements.bat` again. The packaged EXE should not require end-user dependency installation.
