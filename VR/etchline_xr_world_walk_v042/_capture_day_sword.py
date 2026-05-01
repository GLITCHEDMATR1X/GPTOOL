from pathlib import Path
from direct.task import Task
from panda3d.core import Filename
from p3dopenxr.app import XRWorldWalk

app = XRWorldWalk()
out = Path('/mnt/data/xr_world_walk_day_sword_preview.png')
app.player_root.set_pos(18, 22, 0)
app.player_heading = -28
app.elapsed = 188.0
app.update_palette(0.0, force=True)

for i, walker in enumerate(app.walkers[:4]):
    walker.root.set_pos(12 + i * 1.4, 28 + i * 1.2, 0)
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

app.taskMgr.doMethodLater(0.55, step1, 'step1')
app.taskMgr.doMethodLater(1.0, step2, 'step2')
app.taskMgr.doMethodLater(1.35, step3, 'step3')
app.taskMgr.doMethodLater(2.2, shot, 'shot')
app.run()
