# HoloUtopia Citizen Tasks

This folder defines the visible purpose/task queue layer for HoloUtopia citizens.

Safe-edit rule:

- `task_type_catalog.json` and `citizen_task_rules.json` are authored data.
- Runtime queue mutations should be written only into `data/database/utopia/saves/`.
- Panels are read-only inspectors in this pass.

Pass 25 goal: every tiny robot civilian can expose a clear purpose, current task,
next tasks, mood, energy, friends, and target node through a movable snap panel.
