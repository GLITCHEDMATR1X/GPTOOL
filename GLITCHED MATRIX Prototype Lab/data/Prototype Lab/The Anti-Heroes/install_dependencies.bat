@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo [1/5] Creating virtual environment...
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 goto :fail
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :fail

echo [2/5] Upgrading pip tooling...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :fail

echo [3/5] Installing Python dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [4/5] Checking optional FFmpeg support for MP3 transcoding...
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo FFmpeg is not currently on PATH.
    where winget >nul 2>nul
    if not errorlevel 1 (
        echo Attempting optional install via winget...
        winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
    ) else (
        echo Optional install command:
        echo   winget install --id Gyan.FFmpeg -e
    )
) else (
    echo FFmpeg is already available.
)

echo [5/5] Leaving optional MP3 probing disabled by default.
echo Install FFmpeg if you want automatic MP3-to-WAV conversion for this game.

echo Done.
echo.
echo Recommended audio formats for positional SFX: mono WAV, OGG, or OPUS.
echo MP3 replacements can be transcoded automatically when FFmpeg is installed.
echo.
echo Launch command:
echo   .venv\Scripts\python.exe main.py
pause
exit /b 0

:fail
echo.
echo Dependency installation failed.
pause
exit /b 1
