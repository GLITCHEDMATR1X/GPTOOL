@echo off
setlocal
cd /d "%~dp0"
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
call install_fbx_tools.bat
exit /b %errorlevel%
