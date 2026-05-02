from pathlib import Path
from direct.task import Task
from panda3d.core import Filename
from p3dopenxr.app import XRWorldWalk

app = XRWorldWalk()
out = Path('/mnt/data/xr_world_walk_perf_preview.png')

app.hud_visible = True
app.player_root.set_pos(18, 22, 0)
app.player_heading = -18
app.elapsed = 338.0
app.update_palette(0.0, force=True)
app.camera.set_pos(18.1, 20.4, 1.84)
app.camera.look_at(20.0, 26.5, 1.35)

for i, walker in enumerate(app.walkers[:5]):
    walker.root.set_pos(18.8 + i * 1.3, 27.0 + (i % 2) * 1.1, walker.hover_height)
    walker.aggressive = True
    walker.alert_timer = 8.0
    walker.attack_cooldown = 0.15 + i * 0.1


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

app.taskMgr.doMethodLater(0.45, sword_down, 'sword_down')
app.taskMgr.doMethodLater(0.62, sword_up, 'sword_up')
app.taskMgr.doMethodLater(0.9, charge_down, 'charge_down')
app.taskMgr.doMethodLater(1.55, charge_up, 'charge_up')
app.taskMgr.doMethodLater(2.2, snap, 'snap')
app.run()
