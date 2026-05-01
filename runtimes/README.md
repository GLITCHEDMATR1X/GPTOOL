# Portable Runtime Folder

This folder is reserved for reusable sidecar runtimes. The bridge does **not** ship Panda3D binaries by default, but it knows how to use them when you place one here.

Recommended layout:

```text
runtimes/
  panda3d_py313/
    python.exe              # Windows portable Python, or
    Scripts/python.exe      # venv-style Windows runtime, or
    bin/python              # Linux/macOS venv-style runtime
    Lib/
    Scripts/
    site-packages/
```

The runtime should already have Panda3D installed once:

```bash
python -m pip install -r requirements.txt
```

Then use:

```bash
python bridge.py full-pass . --profile panda3d --runtime portable --smoke --entry main.py --require-screenshot
```

You can also keep the runtime outside the tool and point to it:

```bash
python bridge.py panda3d-runtimes . --runtime portable --runtime-path C:\\Tools\\panda3d_py313
```

or set one of these environment variables:

```text
GPT_BRIDGE_PANDA3D_PYTHON=C:\\Tools\\panda3d_py313\\python.exe
GPT_BRIDGE_PANDA3D_RUNTIME=C:\\Tools\\panda3d_py313
```
