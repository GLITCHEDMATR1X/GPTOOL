# TESTED — Pass 11 Playable Simulation Characters

Proof commands are recorded in the delivered proof artifact zip. Expected checks:

- Bridge version reports `0.6.1-pass11`.
- All GPTOOL Python files compile.
- `generate-game` produces a fresh Panda3D project.
- Generated `main.py --settings-check` passes.
- Generated `main.py` compiles.
- Headless proof confirms two playable simulation characters.
- Offscreen screenshot mode writes a PNG backup screenshot where Panda3D offscreen rendering is available.
- Package compare confirms no files from the cleanup baseline were removed.
