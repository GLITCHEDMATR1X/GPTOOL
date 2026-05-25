@echo off
setlocal
cd /d "%~dp0"
echo Starting GPTOOL Automation Task Director...
python automation_tasks\task_menu.py
echo.
pause
