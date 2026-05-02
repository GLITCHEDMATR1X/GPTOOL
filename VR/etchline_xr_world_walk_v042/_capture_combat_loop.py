from pathlib import Path
from direct.task import Task
from panda3d.core import Filename
from p3dopenxr.app import XRWorldWalk

app = XRWorldWalk()
out = Path('/mnt/data/xr_world_walk_combat_loop_preview.png')

app.player_root.set_pos(18, 22, 0)
app.player_heading = -18
app.elapsed = 312.0
app.update_palette(0.0, force=True)
app.camera.set_pos(18.1, 20.4, 1.84)
app.camera.look_at(20.0, 26.5, 1.35)

for i, walker in enumerate(app.walkers[:4]):
    walker.root.set_pos(18.8 + i * 1.15, 27.2 + i * 0.75, walker.hover_height)
    walker.aggressive = True
    walker.alert_timer = 8.0
    walker.attack_cooldown = 0.2 + i * 0.15


def sword_down(task):
    app.keys['fire_left'] = True
    return Task.done


def sword_up(task):
    app.keys['fire_left'] = False
    return Task.done


def charge_down(task):
    app.keys['fire_right'] = True
    return Task.done


def charge_up(task):
    app.keys['fire_right'] = False
    return Task.done


def snap(task):
    app.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
    app.userExit()
    return Task.done

app.taskMgr.doMethodLater(0.52, sword_down, 'sword_down')
app.taskMgr.doMethodLater(0.76, sword_up, 'sword_up')
app.taskMgr.doMethodLater(1.02, charge_down, 'charge_down')
app.taskMgr.doMethodLater(1.86, charge_up, 'charge_up')
app.taskMgr.doMethodLater(2.35, snap, 'snap')
app.run()
