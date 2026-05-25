@echo off
setlocal
cd /d "%~dp0"
python automation_tasks\install_bridge_automation_tasks.py --bridge bridge.py --apply
echo.
pause
