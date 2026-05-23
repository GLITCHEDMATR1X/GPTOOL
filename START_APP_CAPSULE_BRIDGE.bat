@echo off
setlocal
cd /d "%~dp0"
echo Starting GPTOOL App Capsule Bridge...
python app_capsules\app_bridge_menu.py
if errorlevel 1 echo.
if errorlevel 1 echo App Capsule Bridge exited with a warning/error. Check reports/app_capsule.
echo.
pause
