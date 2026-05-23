@echo off
setlocal
cd /d "%~dp0"
echo This will modify bridge.py and create bridge.py.patch_gate.bak.
set /p CONFIRM=Type INSTALL to continue: 
if not "%CONFIRM%"=="INSTALL" (
  echo Cancelled.
  pause
  exit /b 1
)
python patching\install_bridge_patch_gate.py --bridge bridge.py --apply
echo.
pause
