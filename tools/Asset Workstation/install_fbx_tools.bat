@echo off
setlocal
cd /d "%~dp0"
set "TOOLS_DIR=%~dp0tools"
set "ZIP_PATH=%TOOLS_DIR%\FBX2glTF-windows-x86_64.zip"
set "EXTRACT_DIR=%TOOLS_DIR%\FBX2glTF-windows-x86_64"
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"
echo [Panda Asset Workstation] Installing FBX2glTF into %TOOLS_DIR%
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/godotengine/FBX2glTF/releases/download/v0.13.1/FBX2glTF-windows-x86_64.zip' -OutFile '%ZIP_PATH%'"
if errorlevel 1 (
  echo Download failed.
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path '%EXTRACT_DIR%') { Remove-Item -Recurse -Force '%EXTRACT_DIR%' }; Expand-Archive -Path '%ZIP_PATH%' -DestinationPath '%EXTRACT_DIR%' -Force"
if errorlevel 1 (
  echo Extraction failed.
  exit /b 1
)
echo FBX2glTF installed.
exit /b 0
