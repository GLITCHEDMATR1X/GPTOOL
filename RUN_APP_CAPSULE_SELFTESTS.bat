@echo off
setlocal
cd /d "%~dp0"
echo Running GPTOOL App Capsule Bridge self-tests...
python tests\selftest_app_capsules.py
echo.
pause
