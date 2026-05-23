@echo off
setlocal
cd /d "%~dp0"
echo Dry-run bridge.py command hook install...
python patching\install_bridge_patch_gate.py --bridge bridge.py
echo.
pause
