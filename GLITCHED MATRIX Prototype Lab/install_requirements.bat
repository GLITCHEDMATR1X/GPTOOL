@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Installing GLITCHED MATRIX Prototype Lab unified dependencies...
echo Target runtime: Windows 10+ / Python 3.13.x / Panda3D 1.10.16
echo Python 3.12 remains supported by requirements markers for older local dev machines.
echo.

set "PYLAUNCH="
where py >nul 2>nul && py -3.13 -c "import sys" >nul 2>nul && set "PYLAUNCH=py -3.13"
if not defined PYLAUNCH where py >nul 2>nul && set "PYLAUNCH=py -3"
if not defined PYLAUNCH where python >nul 2>nul && set "PYLAUNCH=python"

if not defined PYLAUNCH (
    echo Python was not found. Install Python 3.13.x from python.org, then run this again.
    goto FAIL
)

%PYLAUNCH% -c "import sys; print('Using Python', sys.version.split()[0]); raise SystemExit(0 if sys.version_info >= (3, 13) else 12)"
if errorlevel 12 (
    echo.
    echo WARNING: This project now targets Python 3.13.x for final builds.
    echo The install will continue only if your requirements marker can select a compatible Panda3D wheel.
    echo.
)

%PYLAUNCH% -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto FAIL

%PYLAUNCH% -m pip install --prefer-binary -r requirements.txt
if errorlevel 1 goto FAIL

echo.
%PYLAUNCH% -c "import tkinter, _tkinter; import pygame; import panda3d; from panda3d.core import PandaSystem; import PIL.Image, PIL.ImageTk; import numpy; import mss; import pydub; import reportlab; import trimesh; import cv2; import tkinterdnd2; print('Tk bridge OK'); print('pygame bridge OK'); print('Panda3D', PandaSystem.getVersionString())"
if errorlevel 1 goto FAIL

echo.
echo Done. Press any key to exit.
pause >nul
exit /b 0

:FAIL
echo.
echo Dependency installation failed.
pause >nul
exit /b 1
