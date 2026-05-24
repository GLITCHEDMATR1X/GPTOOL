# Start Here — Anti-Heroes Bridge Testing

Use this file when the Anti-Heroes helper scripts appear to do nothing or close instantly.

## Easiest test

Double-click:

```text
Launch_AntiHeroes_Tools.bat
```

That opens a menu and keeps the terminal window visible so errors do not disappear.

## Menu options

1. **Run static bridge pipeline**
   - Checks Python syntax.
   - Checks whether a GPTOOL human manifest exists.
   - Writes pipeline reports.

2. **Initialize/validate spawn roster**
   - Creates default player/service/contact roster entries.
   - Writes spawn roster reports.

3. **Run state-only runtime adapter proof**
   - Proves the runtime adapter can write state data without launching Panda3D.

4. **Run visual probes with Panda3D**
   - Requires Panda3D.
   - Writes screenshot progress files if Panda3D can render.

5. **Show expected output folders**
   - Prints reports and screenshot folder status.

## Command-line version

From this folder:

```bash
python antiheroes_tools_menu.py
```

Or run the safest direct test:

```bash
python antiheroes_gptool_pipeline.py --static
```

## Important note

These files are bridge/proof tools, not the full Anti-Heroes game runtime. They prepare and test the imported-model pipeline so the live Anti-Heroes city can load GPTOOL-exported models safely later.

If no `assets/characters/humans/human_manifest.json` exists yet, static checks can still run, but model-loading tests will report warnings until a GPTOOL manifest is synced.
