from panda3d.core import loadPrcFileData

loadPrcFileData('', 'window-title Zonez')
loadPrcFileData('', 'win-size 1600 900')
loadPrcFileData('', 'sync-video true')
loadPrcFileData('', 'show-frame-rate-meter false')
loadPrcFileData('', 'default-fov 75')
loadPrcFileData('', 'cursor-hidden true')
loadPrcFileData('', 'textures-power-2 none')

from sandbox_proto.app import SandboxApp


if __name__ == '__main__':
    app = SandboxApp()
    app.run()
