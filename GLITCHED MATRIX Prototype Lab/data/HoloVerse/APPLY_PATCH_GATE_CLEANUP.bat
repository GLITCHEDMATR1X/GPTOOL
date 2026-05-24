@echo off
setlocal
cd /d "%~dp0"
echo GPTOOL Patch Gate cleanup for HoloVerse
for %%P in (
  "Dimensions\HoloUtopia"
  "Dimensions\Etch-Line"
  "logs\latest.log"
  "logs\mode_gateway_audit.json"
  "logs\mode_gateway_history.json"
) do (
  if exist "%%~P" (
    echo Removing %%~P
    rmdir /s /q "%%~P" 2>nul || del /f /q "%%~P" 2>nul
  )
)
for /d /r %%D in (__pycache__) do if exist "%%D" rmdir /s /q "%%D"
for /r %%F in (*.pyc) do if exist "%%F" del /f /q "%%F"
echo Cleanup complete.
pause
