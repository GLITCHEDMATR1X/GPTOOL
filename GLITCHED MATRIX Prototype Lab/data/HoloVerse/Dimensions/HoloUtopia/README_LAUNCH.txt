HoloUtopia standalone launch package - Town Focus vertical slice
================================================================

Use this folder as its own app/test package.

Launch:
  python main.py

Windows helper:
  run_HoloUtopia.bat

Primary entry point:
  HoloUtopia/main.py

Internal runtime modules live under:
  HoloUtopia/data/HoloUtopia/

Authored city database lives under:
  HoloUtopia/data/database/utopia/

Runtime/session state lives under:
  HoloUtopia/data/database/utopia/runtime_state/

The runtime_state folder is generated locally and is intentionally excluded
from patch/drop-in zips. It stores Town Focus session memory only. It does not
replace or mutate authored schedules, citizen data, town JSON, HoloVerse routes,
HoloCore routes, or artifact adapters.

Core loop:
  Full City Overview
    -> click a district/town signal/building
    -> enter isolated Town Focus
    -> inspect events, routes, citizens, activity clusters, or buildings
    -> optionally press 1-4 to influence selected events
    -> press Enter/P to walk the isolated town in first person
    -> use E in first person to interact with citizens, buildings, routes, and events
    -> ESC returns first-person to Town Focus, then Town Focus to City Overview

Camera:
  RMB drag / Arrow keys  orbit around current pivot
  Mouse wheel            zoom in/out around current pivot
  WASD                   pan orbit pivot
  Q / E                  vertical camera adjustment
  Enter / P              enter/exit first-person walk mode from Town Focus
  F                      focus selected building/citizen when available
  V                      cycle view preset

Town Focus camera rule:
  The orbit pivot is the center of the selected town.
  The default angle uses a tighter tilt-shift view intended to show the isolated town.
  Full City Overview pivots around the center of the whole city.

Watcher controls inside Town Focus:
  Mouse1      inspect local event diamonds, route trails, citizens, clusters, or buildings
  Enter/P     first-person walk mode inside the isolated town
  E           in first-person, interact with the crosshair target
  1           Dispatch Help for selected event
  2           Boost Repair for selected event
  3           Calm Civilians for selected event
  4           Fund Supplies for selected event
  F1          toggle quick guide
  Shift+H     alternate quick-guide toggle
  Shift+R     safe-reset Town Focus runtime_state only
  X           close current inspector/detail panel
  ESC         leave Town Focus first, then exits standalone if already in overview

Current slice status:
  - autonomous local Town Focus view exists for all 9 towns
  - local NPC memory, events, orders, consequences, and health reports persist through runtime_state
  - runtime_state is versioned, size-bounded, atomically saved, and safe-resettable
  - city overview uses low-cost district signals instead of simulating every local NPC
  - Industrial Yard Alpha has the first focused district art pass with power/electric plant structures
  - first-person walk mode now exists inside isolated Town Focus without enabling full-city NPC simulation

Safety / packaging notes:
  - Panda3D is required: py -3 -m pip install panda3d
  - Do not include runtime_state in release patches unless explicitly requested.
  - Do not include __pycache__, .pyc, logs, crash_reports, screenshots, or temporary smoke files in patch zips.
  - Normal runtime display should not write authored schedules or authored town/citizen data.
  - This standalone package does not rename itself to HoloVerse and does not contain a HoloVerse main.py.


Pass 80: First-person usability pass lowers the walk camera to human eye height, resets bad overhead saved positions, adds crosshair target hints, prioritizes nearby citizens before broad building hits, and slows walking/jogging for readable town inspection.
