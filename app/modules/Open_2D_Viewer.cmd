@echo off
setlocal
cd /d "%~dp0..\.."
set "VIEWER_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%VIEWER_PYTHON%" (
  "%VIEWER_PYTHON%" app\modules\viewer2d\server.py
) else (
  python app\modules\viewer2d\server.py
)
if errorlevel 1 pause
