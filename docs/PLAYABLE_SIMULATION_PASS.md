# Pass 11 — Playable Simulation Characters

This pass upgrades generated Panda3D templates from static scene proofs into a small playable simulation test mode.

## Added

- Two procedural human test characters are spawned in every generated template.
- The male simulation tester and female simulation tester remain in-world together.
- `Tab` swaps active control between them.
- WASD/arrow movement and Q/E camera rotation remain available.
- `F12` writes a backup screenshot when a real/offscreen window exists.
- `python main.py --screenshot-mode` writes a backup screenshot and exits for automated proof.
- Scene-proof JSON now includes `app_state` with playable character count, active character, positions, controls, and streamed chunk count.

## Conservative constraints

- No external assets are required.
- Procedural bodies are used so generation stays lightweight.
- The previous headless proof path is preserved.
- `Tab` no longer cycles animation because character swapping is more important for edit testing. Animation cycling moved to `C`.
