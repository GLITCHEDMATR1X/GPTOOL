@echo off
setlocal
cd /d "%~dp0"
echo This will edit bridge.py after creating a backup.
echo Review app_capsule_bridge_install_reports first if you have not.
set /p CONFIRM=Type APPLY to continue: 
if /I not "%CONFIRM%"=="APPLY" (
  echo Cancelled.
  pause
  exit /b 1
)
python app_capsules\install_bridge_app_capsules.py --bridge bridge.py --apply
echo.
pause
