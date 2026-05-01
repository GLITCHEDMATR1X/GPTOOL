from pathlib import Path
from direct.task import Task
from panda3d.core import Filename
from p3dopenxr.app import XRWorldWalk

app = XRWorldWalk()
out = Path('/mnt/data/xr_world_walk_blaster_preview.png')


def prep(task):
    app._shoot_blaster('left')
    app._shoot_blaster('right')
    return Task.done


def shot(task):
    app.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
    app.userExit()
    return Task.done

app.taskMgr.doMethodLater(0.9, prep, 'prep')
app.taskMgr.doMethodLater(1.5, shot, 'shot')
app.run()
