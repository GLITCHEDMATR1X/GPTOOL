from pathlib import Path
from direct.task import Task
from panda3d.core import Filename
from p3dopenxr.app import XRWorldWalk

app = XRWorldWalk()
out = Path('/mnt/data/xr_world_walk_combo_preview.png')
app.player_root.set_pos(18, 22, 0)
app.player_heading = -24
app.elapsed = 236.0
app.update_palette(0.0, force=True)

for i, walker in enumerate(app.walkers[:5]):
    walker.root.set_pos(14.0 + i * 1.25, 28.5 + i * 0.82, walker.hover_height)
    walker.aggressive = True
    walker.alert_timer = 5.0


def sword1(task):
    app.keys['fire_left'] = True
    return Task.done

def sword1_up(task):
    app.keys['fire_left'] = False
    return Task.done

def sword2(task):
    app.keys['fire_left'] = True
    app.keys['fire_right'] = True
    return Task.done

def sword2_up(task):
    app.keys['fire_left'] = False
    app.keys['fire_right'] = False
    return Task.done

def sword3(task):
    app.keys['fire_left'] = True
    return Task.done

def sword3_up(task):
    app.keys['fire_left'] = False
    return Task.done

def shot(task):
    app.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
    app.userExit()
    return Task.done

app.taskMgr.doMethodLater(0.45, sword1, 'sword1')
app.taskMgr.doMethodLater(0.58, sword1_up, 'sword1_up')
app.taskMgr.doMethodLater(0.86, sword2, 'sword2')
app.taskMgr.doMethodLater(1.12, sword2_up, 'sword2_up')
app.taskMgr.doMethodLater(1.34, sword3, 'sword3')
app.taskMgr.doMethodLater(1.52, sword3_up, 'sword3_up')
app.taskMgr.doMethodLater(2.28, shot, 'shot')
app.run()
