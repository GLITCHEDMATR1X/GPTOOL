from pathlib import Path
from direct.task import Task
from panda3d.core import Filename
from p3dopenxr.app import XRWorldWalk

app = XRWorldWalk()
out = Path('/mnt/data/xr_world_walk_combat_preview.png')

# face toward a populated district and spawn a shot burst
app.player_root.set_pos(18, 22, 0)
app.player_heading = -35

# pre-arm the scene
for walker in app.walkers[:3]:
    walker.root.set_pos(10 + walker.seed % 6, 34 + (walker.seed % 5) * 1.5, 0)
    walker.aggressive = True
    walker.alert_timer = 5.0


def step1(task):
    app.keys['fire_left'] = True
    return Task.done

def step2(task):
    app.keys['fire_left'] = False
    app.keys['fire_right'] = True
    return Task.done

def step3(task):
    app.keys['fire_right'] = False
    return Task.done

def shot(task):
    app.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
    app.userExit()
    return Task.done

app.taskMgr.doMethodLater(0.4, step1, 'step1')
app.taskMgr.doMethodLater(0.8, step2, 'step2')
app.taskMgr.doMethodLater(1.15, step3, 'step3')
app.taskMgr.doMethodLater(1.9, shot, 'shot')
app.run()
