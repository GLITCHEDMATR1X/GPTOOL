@echo off
setlocal
cd /d "%~dp0"
python tests\selftest_automation_tasks.py
echo.
pause
