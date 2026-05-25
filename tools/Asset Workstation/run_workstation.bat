@echo off
setlocal
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo Workstation exited with an error.
    if exist logs\crash.log (
        echo Crash log: %cd%\logs\crash.log
    )
)
pause
