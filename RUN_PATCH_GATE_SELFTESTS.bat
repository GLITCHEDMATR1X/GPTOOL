@echo off
setlocal
cd /d "%~dp0"
echo Running GPTOOL AI Patch Gate self-tests...
python patching\selftest_pass_combiner.py
if errorlevel 1 goto fail
python patching\selftest_pass_combiner_v4.py
if errorlevel 1 goto fail
python patching\selftest_repo_patch_tool.py
if errorlevel 1 goto fail
echo.
echo Self-tests passed.
goto end
:fail
echo.
echo One or more self-tests failed.
:end
echo.
pause
