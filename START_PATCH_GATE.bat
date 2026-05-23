@echo off
setlocal
cd /d "%~dp0"
echo Starting GPTOOL AI Patch Gate...
python patching\patch_gate_menu.py
if errorlevel 1 echo.
if errorlevel 1 echo Patch Gate exited with a warning/error. Check patch_gate_launcher_logs.
echo.
pause
