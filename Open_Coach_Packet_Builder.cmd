@echo off
setlocal
where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 "%~dp0scripts\packet_ui.py"
    exit /b 0
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0scripts\packet_ui.py"
    exit /b 0
)
echo Python with Tkinter is needed to open this window.
echo Install standard Windows Python, then set up this repository's environment:
echo From this repository folder, run:
echo   py -m venv .venv
echo   .venv\Scripts\python.exe -m pip install -e .
echo Then double-click this launcher again.
pause
exit /b 1
