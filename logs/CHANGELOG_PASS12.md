# Changelog — Pass 12

- Bumped bridge version to `0.6.2-pass12`.
- Added generated-template `--route-proof` simulation mode.
- Route proof automatically moves the male tester, simulates a Tab swap, moves the female tester, and drops visible route markers.
- Scene proof now records route start/end positions, swap count, route marker count, and events.
- Updated validation commands so backup screenshot proof can exercise actual playable controls.
- Made the Panda3D smoke hook exit deterministic after proof capture in headless/offscreen runs.
- Changed generated screenshot mode default window hint to `default` so Panda3D can choose the working fallback display path.
- Generated test/screenshot mode now manually steps Panda3D tasks so proof capture does not depend on an onscreen event loop.
- Added synchronous route-proof execution for generated screenshot mode so movement/swap proof does not depend on realtime task-loop progress.
- Route proof saves the current offscreen buffer directly to avoid blocking render loops in display-less containers.
- Generated automated proof modes use `os._exit(0)` after proof writing to avoid interpreter-finalization hangs in this container.
- Restored two explicit `renderFrame()` calls before route screenshots now that automated proof exits with `os._exit(0)`.
