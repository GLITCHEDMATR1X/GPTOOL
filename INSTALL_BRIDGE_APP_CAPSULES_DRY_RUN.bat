@echo off
setlocal
cd /d "%~dp0"
echo Dry-running bridge.py app capsule command install...
python app_capsules\install_bridge_app_capsules.py --bridge bridge.py
echo.
pause
