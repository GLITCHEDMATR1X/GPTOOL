# Panda Asset Workstation

A desktop workstation and CLI for preparing 3D assets for Panda3D with a GLB-first commercial pipeline.

## What it does

- Imports common mesh formats through Python tooling
- Converts `FBX`, `OBJ`, and `GLB/GLTF` with explicit validation reports
- Prepares Panda-ready exports, especially `.glb`
- Shows model stats, backend choice, and rig-safe versus static-only status
- Re-centers, scales, rotates, and repairs normals
- Edits textures in-app
- Generates seamless offset previews
- Saves edited textures, height maps, and normal maps
- Packages a Panda3D-ready folder with a loader example, logs, preview screenshot, and JSON validation report
- Maintains a workstation layout with logs, exports, and project files

## Best workflow target

Preferred runtime path for Panda3D:

`source asset -> .glb -> Panda3D`

Panda3D's documentation recommends glTF/GLB as the preferred interchange format and recommends the `panda3d-gltf` plug-in for loading glTF at runtime. BAM remains Panda3D's efficient shipping/cache format.

## Current capabilities

### Mesh workstation and converter

- Import: `.glb`, `.gltf`, `.obj`, `.stl`, `.ply`, `.off`
- Attempted import: `.fbx`, `.dae` when the available Python backend can open them
- Export: `.glb`, `.obj`, `.stl`, `.ply`
- Validation stats: vertices, faces, bounds, extents, watertight state, backend used, axis notes
- Export labeling: `rig-safe` only on untouched native/cached GLB paths, otherwise `static-only`
- Fix-up tools: recenter, scale, rotate, normal repair

### Texture lab

- Brightness, contrast, saturation, sharpness, blur
- Seamless offset preview for tiling inspection
- Invert and grayscale toggles
- Save processed texture
- Save height map
- Save normal map

### Panda packaging

- Creates a ready-to-drop package folder
- Copies exported mesh and texture
- Writes `panda_loader_example.py`
- Writes `package.json` metadata
- Copies latest logs into the package
- Writes `validation_report.json` into the package

### CLI

- `python main.py validate <input>`
- `python main.py convert <input> --out <path> --format glb|obj`
- `python main.py package <input> --out <directory>`
- Optional CLI transforms: `--scale`, `--rotate-x`, `--rotate-y`, `--rotate-z`
- Optional overwrite protection: add `--overwrite` only when you mean to replace an existing output

## Important limitations

- This build is intentionally self-contained and does not bundle a full FBX SDK.
- FBX support depends on whichever Python import backend is available in your environment.
- For the most stable Panda3D results, export to `.glb` and load with `panda3d-gltf`. Panda3D's docs say that generic Assimp-based loading quality varies by format, while `panda3d-gltf` is the more mature path.
- Assimp-based imports may come in rotated depending on source coordinate system, which Panda3D documents as a known caveat.
- `OBJ` is treated as static geometry only.
- Candidate exports are written separately from passed-test exports so the last known good outputs are not overwritten by accident.

## Files

- `main.py` - main workstation app and CLI entrypoint
- `run_workstation.bat` - Windows launcher
- `install_requirements.bat` - Windows dependency installer
- `logs/` - latest log and crash log
- `logs/reports/` - JSON validation reports for import, export, package, and CLI runs
- `exports/screenshots/` - preview screenshots from validated runs
- `exports/states/candidate/` - candidate models and packages
- `exports/states/passed_test/` - reserved stable outputs after external runtime validation
- `projects/` - saved workstation project files

## Run

### Windows

1. Run `install_requirements.bat`
2. Run `run_workstation.bat`

### Manual

```bash
python main.py
```

### CLI examples

```bash
python main.py validate "imports\\sample.fbx"
python main.py convert "imports\\sample.obj" --out "exports\\states\\candidate\\models\\sample.glb" --format glb
python main.py package "imports\\sample.glb" --out "exports\\states\\candidate\\packages"
```

### Self-test

```bash
python main.py --selftest
```

The self-test generates a demo mesh and texture, exports them, writes a preview screenshot and JSON validation report, and creates a Panda-ready package folder.
