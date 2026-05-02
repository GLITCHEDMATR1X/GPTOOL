from pathlib import Path
from direct.task import Task
from panda3d.core import Filename
from p3dopenxr.app import XRWorldWalk

app = XRWorldWalk()
out = Path('/mnt/data/xr_world_walk_invert_preview.png')

app.hud_visible = True
app.player_root.set_pos(18, 22, 0)
app.player_heading = -12
app.elapsed = 948.0
app.update_palette(0.0, force=True)
app.camera.set_pos(18.0, 20.1, 1.84)
app.camera.look_at(20.2, 28.0, 1.2)

for i, walker in enumerate(app.walkers[:5]):
    walker.root.set_pos(18.5 + i * 1.5, 27.5 + (i % 2) * 1.3, walker.hover_height)
    walker.aggressive = True
    walker.alert_timer = 8.0


def sword_down(task):
    app.keys['fire_left'] = True
    return Task.done


def sword_up(task):
    app.keys['fire_left'] = False
    return Task.done


def snap(task):
    app.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
    app.userExit()
    return Task.done

app.taskMgr.doMethodLater(0.4, sword_down, 'sword_down')
app.taskMgr.doMethodLater(0.58, sword_up, 'sword_up')
app.taskMgr.doMethodLater(1.9, snap, 'snap')
app.run()
