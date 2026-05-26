@echo off
setlocal
cd /d "%~dp0"
python maintenance\cleanup_gptool_workspace.py
echo.
pause
