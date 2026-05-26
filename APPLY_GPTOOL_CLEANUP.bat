@echo off
setlocal
cd /d "%~dp0"
echo This will remove stale GPTOOL notes/logs/reports/cache and managed project copies if present.
echo Type APPLY to continue.
set /p TOKEN=Approval: 
python maintenance\cleanup_gptool_workspace.py --apply --approval %TOKEN%
echo.
pause
