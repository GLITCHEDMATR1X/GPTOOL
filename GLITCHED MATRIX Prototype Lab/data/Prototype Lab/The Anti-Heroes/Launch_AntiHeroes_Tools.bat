@echo off
setlocal
cd /d "%~dp0"
title Anti-Heroes GPTOOL Bridge Tools

echo ============================================================
echo  Anti-Heroes GPTOOL Bridge Tools
echo ============================================================
echo.
echo This launcher keeps the window open so errors are visible.
echo Folder:
echo   %CD%
echo.

set PYTHON_CMD=python
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo ERROR: Python was not found on PATH.
    echo Install Python or run this from a terminal where python works.
    echo.
    pause
    exit /b 1
  ) else (
    set PYTHON_CMD=py
  )
)

%PYTHON_CMD% antiheroes_tools_menu.py
set EXIT_CODE=%ERRORLEVEL%
echo.
echo Launcher finished with exit code %EXIT_CODE%.
echo.
pause
exit /b %EXIT_CODE%
