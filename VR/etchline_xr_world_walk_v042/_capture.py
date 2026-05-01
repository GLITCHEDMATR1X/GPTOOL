from pathlib import Path
from direct.task import Task
from panda3d.core import Filename
from p3dopenxr.app import XRLab

app = XRLab()
out = Path('/mnt/data/etchline_xr_play_lab_v030_screenshot.png')

def shot(task):
    app.win.saveScreenshot(Filename.fromOsSpecific(str(out)))
    app.userExit()
    return Task.done

app.taskMgr.doMethodLater(1.5, shot, 'shot')
app.run()
