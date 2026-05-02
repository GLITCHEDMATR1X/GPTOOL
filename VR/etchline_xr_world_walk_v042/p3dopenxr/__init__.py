from .version import __version__

__all__ = ['P3DOpenXR', '__version__', 'main']


def __getattr__(name):
    if name == 'P3DOpenXR':
        from .p3dopenxr import P3DOpenXR
        return P3DOpenXR
    if name == 'main':
        from .app import main
        return main
    raise AttributeError(name)
