@echo off
setlocal
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0"
if not exist build mkdir build
cl /nologo /std:c++17 /EHsc /W4 /O2 /DUNICODE /D_UNICODE control_guard.cpp /Fo:build/control_guard.obj /Fe:build/control_guard.exe /link Fwpuclnt.lib Rpcrt4.lib
exit /b %errorlevel%
