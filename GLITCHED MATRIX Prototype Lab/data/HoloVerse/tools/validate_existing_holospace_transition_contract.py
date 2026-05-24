#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
main = (ROOT / 'main.py').read_text(encoding='utf-8')
travel = (ROOT / 'holospace_travel_sequence.py').read_text(encoding='utf-8')

errors = []

def need(cond, msg):
    if not cond:
        errors.append(msg)

need('VERSION = "0.10.96-existing-holospace-transition-corrected"' in main, 'main.py version was not updated for pass 96')
need('from holospace_travel_sequence import HoloSpaceTravelSequence' in main, 'HoloSpace transition must use existing Liquid Orb transition module')
ensure_body = re.search(r'def ensure_holospace_travel_runtime\(self\):(?P<body>.*?)\n    def set_holospace_transition_hud_suppressed', main, re.S)
need(ensure_body is not None, 'ensure_holospace_travel_runtime block missing')
if ensure_body:
    body = ensure_body.group('body')
    need('holospace_warp_transition' not in body, 'ensure_holospace_travel_runtime still imports the replacement warp layer')
    need('duration=float(getattr(self, "holospace_transition_duration", 10.0) or 10.0)' in body, 'transition runtime should default to the original 10-second countdown duration')

need('self.holospace_transition_duration = 10.0' in main, 'HoloSpace transition duration should be 10 seconds by default')
need('"bridge_transition_root", "help_overlay", "comfort_overlay"' in main, 'transition HUD suppression must hide non-countdown overlay roots')
need('"bot_dialogue_root", "safety_exit_root"' in main, 'transition HUD suppression must hide dialogue/safety overlay roots')
need('self.start_holospace_travel_sequence(entry, source="matrixcore_rmb", destination="space")' in main, 'RMB MatrixCore must enter HoloSpace through the existing transition route')
need('self.start_holospace_travel_sequence(entry, source=source, destination="hub")' in main, 'Dyson return must use the same transition route')
need('self.apply_holospace_world_isolation(True, force_space=True)' in main, 'HoloSpace transition must hide the hub/surface world and expose the space layer')
need('self.root_3d.hide()' in main, 'HoloSpace transition must hide the normal HoloVerse world root while the Liquid Orb layer runs')
need('self.root_3d.show()' in main, 'HoloSpace transition completion/cancel must restore the world root')

need('The player can still look around inside the transition' in travel, 'transition module should document camera-look ownership')
need('self.help_label = None' in travel, 'HoloSpace transition help label should be disabled')
need('SPACE TRANSIT //' not in travel, 'HoloSpace transition must not display the old status UI text')
need('WASD bends light' not in travel, 'HoloSpace transition must not display control help text')
need('self.countdown_label["text"] = str(max(1, int(math.ceil(remaining))))' in travel, 'HoloSpace transition countdown should be the only visible UI text')
need('frameColor=(0, 0, 0, 0)' in travel, 'countdown must not use a solid frame panel')
need('HOLOSPACE_TRANSITION_SHADER", "off"' in travel, 'transition shader should default off so the Liquid Orb layer cannot wash out white')
need('app.camera.setHpr' in travel and 'look_pitch' in travel and 'look_yaw' in travel, 'transition should keep camera look movement active')

if errors:
    print('FAIL: existing HoloSpace transition contract')
    for e in errors:
        print(' -', e)
    raise SystemExit(1)
print('OK: existing HoloSpace transition contract')
